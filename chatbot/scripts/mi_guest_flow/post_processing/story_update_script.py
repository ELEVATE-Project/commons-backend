import asyncio
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.utils.timezone import make_aware
from jinja2 import Template

from chatbot.models import (
    Story,
    ChatSession,
    SessionFlowName,
    CompanyBot,
    Voice,
    VoiceType,
    CompanyChat,
    BotVernacular, LLMProvider,
)
from chatbot.models.geo_models import ProfileAddress
from chatbot.utils.chat_utils import get_guided_chat
from chatbot.utils.sql_utils import get_todays_date
from chatbot.utils.story_utils.common.generic_story_tasks import (
    save_generic_story,
    translate_to_english_if_needed
)
from chatbot.utils.story_utils.get_story_prompts import (
    get_tool_values,
)
from chatbot.utils.story_utils.story_llm import generate_story_llm

logger = logging.getLogger("django")

def get_creation_promt(company_bot, profile, session_id):
    context = company_bot.context
    address = ProfileAddress.objects.filter(profile=profile)

    state_machines = company_bot.companystatemachine_set.all().order_by('step')
    master_question = None

    if state_machines.exists():
        first_state_machine = state_machines.first()
        if first_state_machine.bot_question and first_state_machine.bot_question.strip():
            master_question = first_state_machine.bot_question.strip()

    story = Story.objects.filter(session=session_id).first()
    if not story:
        print("No story found!!!")
        return {}

    context_data = {
        "profile": profile,
        "address": address if address else [{}],
        "story": story
    }

    if master_question:
        context_data["master_question"] = master_question

    template = Template(company_bot.tag_context)
    tag_context = template.render(context_data)

    end_context = company_bot.end_context
    project_data = ''
    today_date = get_todays_date(company_bot=company_bot)

    content_prompt = f"""
                {context}
                {tag_context}
                {today_date}
                {project_data}
            """ if context else None
    story_prompt = f"""
                {end_context}
                {tag_context}
                {today_date}
                {project_data}
            """ if end_context else None
    formatted_content_prompt = []
    formatted_story_prompt = []

    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        formatted_content_prompt = [
            {
                'text': content_prompt
            },
        ] if content_prompt else None
        formatted_story_prompt = [
            {
                'text': story_prompt
            },
        ] if story_prompt else None
    elif company_bot.provider == LLMProvider.OPENAI:
        formatted_content_prompt = [
            {
                'role': 'system',
                'content': content_prompt
            },
        ] if content_prompt else None
        formatted_story_prompt = [
            {
                'role': 'system',
                'content': story_prompt
            },
        ] if story_prompt else None

    return formatted_content_prompt, formatted_story_prompt, tag_context, project_data


def get_validation_prompt(
        response_json_story, validate_bot, response_json_content, tag_context, project_data, profile, session_id
):
    address = ProfileAddress.objects.filter(profile=profile)

    state_machines = validate_bot.companystatemachine_set.all().order_by('step')
    master_question = None

    if state_machines.exists():
        first_state_machine = state_machines.first()
        if first_state_machine.bot_question and first_state_machine.bot_question.strip():
            master_question = first_state_machine.bot_question.strip()


    story = Story.objects.filter(session=session_id).first()
    if not story:
        print("No story found!!!")
        return {}

    validate_context_data = {
        "story_json_output": response_json_story,
        "profile": profile,
        "address": address if address else [{}],
        "story": story,
    }

    if master_question:
        validate_context_data["master_question"] = master_question

    validate_template = Template(validate_bot.tag_context)
    validate_tag_context = validate_template.render(validate_context_data)

    today_date = get_todays_date(company_bot=validate_bot)

    validate_story_prompt = f"""
               {validate_bot.end_context}
               {validate_tag_context}
               {tag_context}
                {today_date}
               {project_data}
           """ if validate_bot.end_context else None

    validate_context_data = {
        "story_json_output": response_json_content,
        "story": story,
        "profile": profile,
        "address": address if address else [{}]
    }

    if master_question:
        validate_context_data["master_question"] = master_question

    validate_tag_context = validate_template.render(validate_context_data)

    print("="*70)
    print("response_json_content: ", response_json_content)
    print("validate_tag_context: ", validate_tag_context)
    print("="*70)
    validate_content_prompt = f"""
               {validate_bot.context}
               {validate_tag_context}
               {tag_context}
                {today_date}
               {project_data}
           """ if validate_bot.context else None

    if validate_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        validate_content_prompt = [
            {
                'text': validate_content_prompt
            },
        ] if validate_content_prompt else None
        validate_story_prompt = [
            {
                'text': validate_story_prompt
            },
        ] if validate_story_prompt else None
    elif validate_bot.provider == LLMProvider.OPENAI:
        validate_content_prompt = [
            {
                'role': 'system',
                'content': validate_content_prompt
            },
        ] if validate_content_prompt else None
        validate_story_prompt = [
            {
                'role': 'system',
                'content': validate_story_prompt
            },
        ] if validate_story_prompt else None

    return validate_content_prompt, validate_story_prompt

def resolve_date_range(start_date=None, end_date=None):
    if start_date and end_date:
        return make_aware(start_date), make_aware(end_date)

    yesterday = datetime.now() - timedelta(days=1)
    start = make_aware(datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0))
    end = make_aware(datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59))
    return start, end


def get_sessions_from_story_flow(start_date=None, end_date=None):
    start_time, end_time = resolve_date_range(start_date, end_date)

    session_ids = (
        Story.objects
        .filter(
            created_at__range=(start_time, end_time),
            other_params__flow=SessionFlowName.GuestMiStory
        )
        .values_list("session", flat=True)
    )

    sessions = (
        ChatSession.objects
        .filter(session__in=session_ids)
        .select_related("profile")
    )

    logger.info(f"Fetched {len(sessions)} sessions")
    print(f"[INFO] Fetched {len(sessions)} sessions")

    return list(sessions)


def process_session(session, access_token):
    try:
        session_id = session.session
        profile = session.profile
        language = session.language or "en"

        logger.info(f"Processing session {session_id}")
        print(f"[INFO] Processing session {session_id}")

        company_bot = CompanyBot.objects.get(route="/mi_story_update")
        validate_bot = CompanyBot.objects.get(route="/mi_story_update_validate")

        voice_provider = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.TextToText,
            language=language
        ).first()

        company_chats = CompanyChat.objects.filter(
            session=session_id
        ).order_by("created_at")

        intro_to_pass = None
        flow_bot = CompanyBot.objects.get(company=profile.company, route="/guided_guest")
        bot_vernacular = BotVernacular.objects.filter(company_bot=flow_bot).first()

        if bot_vernacular:
            intro_to_pass = (
                bot_vernacular.introductory_message
                if access_token else
                bot_vernacular.alt_introductory_message
            )

        messages = get_guided_chat(
            company_bot=company_bot,
            company_chats=company_chats,
            intro=intro_to_pass
        )

        formatted_content_prompt, formatted_story_prompt, _, _ = get_creation_promt(
            company_bot=company_bot,
            profile=profile,
            session_id=session_id
        )

        tool_content, tool_story = get_tool_values(company_bot=company_bot)

        logger.info(f"Calling primary LLM for session {session_id}")
        print(f"[INFO] Calling primary LLM for session {session_id}")

        response_json_content, _ = asyncio.run(
            generate_story_llm(
                formatted_content_prompt=formatted_content_prompt,
                formatted_story_prompt=formatted_story_prompt,
                messages=messages,
                tool_content=tool_content,
                tool_story=tool_story,
                company_bot=company_bot,
                flow=SessionFlowName.GuestMiStory
            )
        )

        if not isinstance(response_json_content, dict):
            logger.error(f"Initial LLM response is not JSON for session {session_id}")
            print(f"[ERROR] Initial LLM response is not JSON for session {session_id}")
            raise Exception("Initial LLM response is not JSON")

        validate_content_prompt, validate_story_prompt = get_validation_prompt(
            response_json_story=response_json_content,
            validate_bot=validate_bot,
            response_json_content=response_json_content,
            tag_context="",
            project_data="",
            profile=profile,
            session_id=session_id
        )

        print("=" * 70)
        print("validate_content_prompt:")
        print(validate_content_prompt)
        print("=" * 70)

        tool_content, tool_story = get_tool_values(company_bot=validate_bot)

        logger.info(f"Calling validation LLM for session {session_id}")
        print(f"[INFO] Calling validation LLM for session {session_id}")

        validated_response, _ = asyncio.run(
            generate_story_llm(
                formatted_content_prompt=validate_content_prompt,
                formatted_story_prompt=validate_story_prompt,
                messages=messages,
                tool_content=tool_content,
                tool_story=tool_story,
                company_bot=validate_bot,
                flow=SessionFlowName.GuestMiStory
            )
        )

        if isinstance(validated_response, dict):
            response_json_content = validated_response
        else:
            logger.error(f"Validation LLM returned invalid JSON for session {session_id}")
            print(f"[ERROR] Validation LLM returned invalid JSON for session {session_id}")
            raise Exception("Validation LLM failed")

        if "challenge" in response_json_content:
            response_json_content.setdefault(
                "problem_statement",
                response_json_content.get("challenge")
            )

            response_json_content.pop("challenge", None)

        logger.info(f"Saving story for session {session_id}")
        print(f"[INFO] Saving story for session {session_id}")

        save_generic_story(
            response_json_story=response_json_content,
            language=language,
            voice_provider=voice_provider,
            profile=profile,
            session=session_id,
            combined_reason="",
            flow=SessionFlowName.GuestMiStory,
            company_bot=company_bot,
            exclude_fields=['problem_statement', 'user_name', 'title']
        )

        if response_json_content.get("problem_statement"):
            from shikshalokam.models import Project, ProjectVernacular
            from chatbot.utils.story_utils.format_utils import clean_escaped_text
            from chatbot.utils.story_llama_utils import translate_field
            import json

            raw_problem = response_json_content.get("problem_statement", "")
            raw_title = response_json_content.get("title", "")

            english_problem = clean_escaped_text(
                translate_to_english_if_needed(raw_problem, voice_provider, language)
            )
            english_title = clean_escaped_text(
                translate_to_english_if_needed(raw_title, voice_provider, language)
            )

            story = Story.objects.filter(session=session_id).first()
            if not story:
                return session_id, True

            project = Project.objects.filter(story=story).first()
            if not project:
                return session_id, True

            project.actual_problem_statement = english_problem
            project.actual_title = english_title
            project.save(update_fields=["actual_problem_statement", "actual_title"])

            if language != "en":
                translated_problem = translate_field(
                    voice_provider, english_problem, language, "en"
                )
                translated_title = translate_field(
                    voice_provider, english_title, language, "en"
                )

                project_vernacular, _ = ProjectVernacular.objects.get_or_create(
                    project=project,
                    language=language,
                    defaults={"details": "{}"}
                )

                details = json.loads(project_vernacular.details or "{}")
                details.setdefault("project", {})
                details["project"].update({
                    "actual_problem_statement": translated_problem,
                    "actual_title": translated_title
                })

                project_vernacular.details = json.dumps(details)
                project_vernacular.save(update_fields=["details"])

        logger.info(f"Session {session_id} processed successfully")
        print(f"[INFO] Session {session_id} processed successfully")

        return session_id, True

    except Exception as e:
        logger.error(f"Failed for session {session.session}: {str(e)}", exc_info=True)
        print(f"[ERROR] Failed for session {session.session}: {str(e)}")
        return session.session, False


def create_stories_parallel(sessions, access_token, max_workers=4):
    succeeded = []
    failed = []

    logger.info(f"Running with ThreadPoolExecutor (workers={max_workers})")
    print(f"[INFO] Running with ThreadPoolExecutor (workers={max_workers})")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_session, session, access_token)
            for session in sessions
        ]

        for future in as_completed(futures):
            session_id, success = future.result()
            if success:
                succeeded.append(session_id)
            else:
                failed.append(session_id)

    logger.info(f"Success count: {len(succeeded)}")
    logger.info(f"Failure count: {len(failed)}")
    print(f"[INFO] Success count: {len(succeeded)}")
    print(f"[INFO] Failure count: {len(failed)}")

    return succeeded, failed


def run_story_update_from_temp_bot(
    access_token,
    start_date=None,
    end_date=None,
    max_workers=4,
    session_ids=None
):
    logger.info("Starting story update pipeline")
    print("[INFO] Starting story update pipeline")

    if session_ids:
        sessions = (
            ChatSession.objects
            .filter(session__in=session_ids)
            .select_related("profile")
        )
    else:
        sessions = get_sessions_from_story_flow(start_date, end_date)

    if not sessions:
        logger.info("No sessions found to process")
        print("[INFO] No sessions found to process")
        return [], []

    succeeded, failed = create_stories_parallel(
        sessions=sessions,
        access_token=access_token,
        max_workers=max_workers
    )

    logger.info(f"Pipeline completed. Success: {len(succeeded)}, Failed: {len(failed)}")
    print(f"[INFO] Pipeline completed. Success: {len(succeeded)}, Failed: {len(failed)}")

    return succeeded, failed
