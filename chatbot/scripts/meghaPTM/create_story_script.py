from chatbot.models import (Profile, CompanyChat,
                            ChatSession, ChatStatus, BotVernacular)
from chatbot.utils.chat_utils import get_guided_chat
from chatbot.utils.shikshalokam_mitra_utils import get_stored_conversation, get_stored_chathistory
from chatbot.utils.shikshalokam_story_utils import save_shikshalokam_story

from chatbot.utils.story_utils.format_utils import get_formatted_story
from chatbot.utils.story_utils.get_story_prompts import get_creation_promt, get_tool_values, \
    get_validation_prompt


from chatbot.llm_models.llm_script import handle_bedrock_model
import traceback
from chatbot.models import StoryStatusChoices, Story, CompanyBot, Voice, \
    VoiceType
from chatbot.models.geo_models import ProfileAddress
from chatbot.utils.story_llama_utils import translate_field, create_project
from chatbot.utils.story_utils.challenges_utils import handle_challenges_solutions
from chatbot.utils.story_utils.format_utils import clean_escaped_text
from chatbot.utils.story_utils.story_llm import generate_story_llm
from chatbot.utils.story_utils.story_utils import get_story_company_bot
from chatbot.utils.transliterate_utils import transliterate_text
from shikshalokam.models import Project, Task
from shikshalokam.serializer import TaskSerializer

import asyncio
import functools
from chatbot.models import LLMProvider, SessionFlowName
import logging


import json
import os
from django.core.validators import URLValidator
import json_repair


logger = logging.getLogger('django')
validate = URLValidator()
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER'))



logger = logging.getLogger('django')

def process_mega_ptm_sessions(limit=0):
    """
    Process all 'megaPTM' sessions that do not have a corresponding story.
    Categorize sessions into success, failed, or in doubt.
    """

    success_sessions = []
    failed_sessions = []
    in_doubt_sessions = []

    sessions = ChatSession.objects.filter(
        session_type='megaPTM'
    ).exclude(
        session__in=Story.objects.values_list('session', flat=True)
    )

    if limit > 0:
        sessions = sessions[:limit]

    print(f"Found {sessions.count()} sessions to process.\n")

    for session in sessions:
        try:
            profile_id = session.profile.id if session.profile else None
            session_id = session.session
            flow = session.session_type
            language = 'en'
            access_token = None

            print(f"Processing session: {session_id} with profile: {profile_id}")

            story_id, story_content, err_msg = create_story_object(
                profile_id, session_id, access_token, flow, language
            )

            if story_id:
                try:
                    story = Story.objects.get(id=story_id)
                    other_params = story.other_params or {}

                    user_name = other_params.get("user_name", "").strip()
                    ptm_summary = other_params.get("ptm_experience_summary", "").strip()

                    if user_name and ptm_summary and user_name!='' and ptm_summary !='':
                        success_sessions.append(session_id)
                        print(f"✅ Successfully processed session: {session_id}\n")
                    else:
                        in_doubt_sessions.append(session_id)
                        print(f"❓ In doubt: session {session_id} has missing fields.\n")

                except Story.DoesNotExist:
                    failed_sessions.append(session_id)
                    print(f"❌ Story not found for session: {session_id}\n")
            else:
                failed_sessions.append(session_id)
                print(f"❌ Story creation failed for session: {session_id} — {err_msg}\n")

        except Exception as e:
            failed_sessions.append(session.session)
            print(f"❌ Exception while processing session {session.session}: {str(e)}\n")

    # Summary
    print("\n--- Summary ---")
    print(f"✅ Success Count: {len(success_sessions)}")
    print(f"❌ Failure Count: {len(failed_sessions)}")
    print(f"❓ In Doubt Count: {len(in_doubt_sessions)}")

    print("\nSuccessful Sessions:\n", success_sessions)
    print("\nFailed Sessions:\n", failed_sessions)
    print("\nIn Doubt Sessions:\n", in_doubt_sessions)

    return {
        "success": success_sessions,
        "failed": failed_sessions,
        "in_doubt": in_doubt_sessions,
    }


# Example usage:
# process_mega_ptm_sessions()         # Process all
# process_mega_ptm_sessions(limit=1)  # Only process first session



def create_story_object(profile_id, session, access_token, flow, language='en'):
    voice_provider=None
    company_bot=None
    try:
        profile = Profile.objects.filter(id=profile_id).first()
        company_chats = CompanyChat.objects.filter(session=session).order_by('created_at')

        company_bot, validate_bot = get_story_company_bot(profile=profile, flow=flow)

        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText, language=language
        ).first()

        chat_session = ChatSession.objects.get(session=session)

        formatted_content_prompt, formatted_story_prompt, tag_context, project_data = get_creation_promt(
            company_bot=company_bot, profile=profile
        )

        intro_to_pass = None

        if flow and flow in [SessionFlowName.GuestMiStory]:
            flow_company_bot = CompanyBot.objects.get(company=profile.company, route='/guided_guest')
            bot_vernacular = BotVernacular.objects.filter(company_bot=flow_company_bot).first()
            if bot_vernacular:
                intro_to_pass = bot_vernacular.introductory_message

        messages = get_guided_chat(
            company_bot=company_bot, company_chats=company_chats, intro=intro_to_pass
        )

        tool_content, tool_story = get_tool_values(company_bot=company_bot)

        response_json_content, response_json_story = asyncio.run(
            generate_story_llm(
                formatted_content_prompt=formatted_content_prompt, formatted_story_prompt=formatted_story_prompt,
                messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=company_bot,
                flow=flow
            )
        )

        validate_content_prompt, validate_story_prompt = get_validation_prompt(
            response_json_story=response_json_story, validate_bot=validate_bot,
            response_json_content=response_json_content, tag_context=tag_context, project_data=project_data,
            profile=profile
        )

        tool_content, tool_story = get_tool_values(company_bot=validate_bot)

        if company_bot.provider != validate_bot.provider:
            messages = get_guided_chat(
                company_bot=validate_bot, company_chats=company_chats, intro=intro_to_pass
            )

        response_json_story, combined_reason = asyncio.run(
            validate_story_llm(
                formatted_content_prompt=validate_content_prompt, formatted_story_prompt=validate_story_prompt,
                messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=validate_bot,
                flow=flow
            )
        )
        if flow in [SessionFlowName.LoginMiStory, SessionFlowName.GuestMiStory, SessionFlowName.Reflection,
                    SessionFlowName.SsoFlow]:
            story, problem_statement = save_story(
                response_json_story=response_json_story, language=language, voice_provider=voice_provider,
                profile=profile, session=session, combined_reason=combined_reason, flow=flow,
                project_id=chat_session.project_id, company_bot=company_bot
            )
        elif flow == SessionFlowName.megaPTM:
            story, problem_statement = save_ptm_story(
                response_json_story=response_json_story, language=language, voice_provider=voice_provider,
                profile=profile, session=session, combined_reason=combined_reason, flow=flow,
                company_bot=company_bot
            )
        else:
            story, problem_statement = save_chaupal_report(
                response_json_story=response_json_story, language=language, voice_provider=voice_provider,
                profile=profile, session=session, combined_reason=combined_reason, flow=flow,
                messages=messages, company_bot=company_bot
            )
        if story:
            formatted_content = get_formatted_story(story)
            if formatted_content:
                story.formatted_content = formatted_content
                story.save(update_fields=['formatted_content'])

        chat_session.session_status = ChatStatus.COMPLETED
        chat_session.save(update_fields=['session_status'])
        chat_session.save_title(language=language)

        if flow == SessionFlowName.Reflection:
            conversation = get_stored_conversation(company_chats=company_chats)
            chat_history = get_stored_chathistory(company_chats=company_chats)
        else:
            conversation, chat_history = [], []

        save_shikshalokam_story(
            story=story, profile=profile,
            problem_statement=problem_statement, chat_history=chat_history, access_token=access_token,
            project_id=None, session=session, conversation=conversation, flow=flow
        )

        story_id = story.id if story and story.id else ""
        story_content = story.content if story and story.content else ""

        return story_id, story_content, ""

    except Exception as e:
        traceback.print_exc()
        if not company_bot:
            profile = Profile.objects.filter(id=profile_id).first()
            company_bot, validate_bot = get_story_company_bot(flow=flow)

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = bot_vernacular.error_message if bot_vernacular and bot_vernacular.error_message \
            else "Please try again!"
        if voice_provider and language != 'en':
            error_message = translate_field(
                voice_provider=voice_provider, message_body=error_message, target_language=language
            )
        return "", "", error_message


def save_story(
        response_json_story, language, voice_provider, profile, session, combined_reason, flow=None, project_id=None,
        company_bot=None
):
    try:
        title = response_json_story['title']
        tweet = response_json_story.get('tweet', '')
        objective = response_json_story['objective']
        action_steps = response_json_story['action_steps']
        impact = response_json_story.get('impact', '')
        micro_improvement = response_json_story.get('micro_improvement', '')
        problem_statement = response_json_story['problem_statement']

        duration = response_json_story.get('duration', '')

        content = response_json_story['content']
        blurb = response_json_story.get('blurb', '')
        content = clean_escaped_text(text=content)
        title = clean_escaped_text(text=title)
        objective = clean_escaped_text(text=objective)
        blurb = clean_escaped_text(text=blurb)
        impact = clean_escaped_text(text=impact)
        problem_statement = clean_escaped_text(text=problem_statement)

        if flow and flow in [SessionFlowName.GuestMiStory]:
            user_name = response_json_story.get('user_name', '')
            location = response_json_story.get('location', '')
            organization = response_json_story.get('organization', '')
            designation = response_json_story.get('designation', '')
        else:
            user_name=profile.first_name if profile and profile.first_name else ''
            organization=None
            designation=None
            location = None
            if profile:
                address = ProfileAddress.objects.filter(profile=profile).first()
                if address:
                    location_parts = filter(None, [address.block, address.district, address.state])
                    location = ", ".join(location_parts)
                else:
                    location = ""

        if not title or not objective or not action_steps or not problem_statement:
            raise Exception("Empty fields found")

        logger.info(f"language used: %s", language)
        if language != 'en':
            title = translate_field(
                voice_provider=voice_provider, message_body=title, target_language=language
            )
            tweet = translate_field(
                voice_provider=voice_provider, message_body=tweet, target_language=language
            )
            objective = translate_field(
                voice_provider=voice_provider, message_body=objective, target_language=language
            )
            if isinstance(action_steps, str):
                action_steps = translate_field(
                    voice_provider=voice_provider, message_body=action_steps, target_language=language
                )
            else:
                action_steps = [
                    translate_field(
                        voice_provider=voice_provider,
                        message_body=action_step,
                        target_language=language
                    )
                    for action_step in action_steps
                ]

            impact = translate_field(
                voice_provider=voice_provider, message_body=impact, target_language=language
            )
            micro_improvement = translate_field(
                voice_provider=voice_provider, message_body=micro_improvement, target_language=language
            )
            problem_statement = translate_field(
                voice_provider=voice_provider, message_body=problem_statement, target_language=language
            )
            content = translate_field(
                voice_provider=voice_provider, message_body=content, target_language=language
            )
            blurb = translate_field(
                voice_provider=voice_provider, message_body=blurb, target_language=language
            )
            if flow and flow in [SessionFlowName.GuestMiStory] and company_bot:
                voice_transliterate_provider = Voice.objects.filter(
                    company_bot=company_bot, type=VoiceType.Transliterate, language=language
                ).first()

                if user_name and user_name != '':
                    is_sentence = ' ' in user_name
                    user_name = transliterate_text(
                        voice_provider=voice_transliterate_provider, message_body=user_name, target_language=language,
                        source_language='en',
                        is_sentence=is_sentence
                    )
                    user_name = get_transliteration_output(data=user_name)
                if organization and organization != '':
                    is_sentence = ' ' in organization
                    organization = transliterate_text(
                        voice_provider=voice_transliterate_provider, message_body=organization,
                        target_language=language,
                        source_language='en',
                        is_sentence=is_sentence
                    )
                    organization = get_transliteration_output(data=organization)
                if designation and designation != '':
                    is_sentence = ' ' in designation
                    designation = transliterate_text(
                        voice_provider=voice_transliterate_provider, message_body=designation,
                        target_language=language,
                        source_language='en',
                        is_sentence=is_sentence
                    )
                    designation = get_transliteration_output(data=designation)


        if flow == SessionFlowName.Reflection and project_id:
            logger.info(f"project_id: %s", project_id)
            project = Project.objects.get(project_id=project_id)
            if project:
                tasks = Task.objects.filter(project=project)
                serialized_tasks = TaskSerializer(tasks, many=True).data
                # action_steps = [task.get('task_name') for task in serialized_tasks]
                action_steps = [f"{idx + 1}. {task.get('task_name')}" for idx, task in enumerate(serialized_tasks)]

        other_params = {
            'duration': duration,
            'flow': flow,
            'user_name': user_name,
        }

        if flow and flow in [SessionFlowName.GuestMiStory]:
            other_params['user_name'] = user_name
            other_params['location'] = location
            other_params['organization'] = organization
            other_params['designation'] = designation

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = title
            story.content = content
            story.tweet = tweet
            story.author = profile
            story.objective = objective
            story.action_steps = action_steps
            story.impact = impact
            story.micro_improvement = micro_improvement
            story.language = language
            story.stage = StoryStatusChoices.COMPLETED
            story.other_params = other_params
            story.location = location if location else ""
            story.blurb = blurb
            story.validation_logs = combined_reason
        else:
            story = Story(
                title=title,
                content=content,
                tweet=tweet,
                author=profile,
                session=session,
                objective=objective,
                action_steps=action_steps,
                impact=impact,
                micro_improvement=micro_improvement,
                language=language,
                stage=StoryStatusChoices.COMPLETED,
                other_params=other_params,
                location=location if location else "",
                blurb=blurb,
                validation_logs=combined_reason
            )
        story.save()

        create_project(
            response_json=response_json_story, title=title, objective=objective, story=story,
            profile=profile, problem_statement=problem_statement, language=language, voice_provider=voice_provider,
            project_id=project_id
        )

        return story, problem_statement
    except Exception as e:
        logger.error('Error Occured: %s', e, exc_info=True)
        traceback.print_exc()
        raise Exception("Failed to save mi story")


def save_chaupal_report(
        response_json_story, language, company_bot, voice_provider, profile, session, combined_reason, flow=None, messages=[]
):
    try:
        title = response_json_story['title']
        challenges_faced = response_json_story['challenges_faced']
        solutions_discussed = response_json_story['solutions_discussed']

        user_name = response_json_story.get('user_name', '')
        user_location = response_json_story.get('location', '')
        organization = response_json_story.get('organization', '')
        participants_count = response_json_story.get('participants_count', '')
        discussion_date = response_json_story.get('discussion_date', '')

        title = clean_escaped_text(text=title)
        if solutions_discussed and len(solutions_discussed) > 0 and challenges_faced and len(challenges_faced) > 0:
            challenges_faced, solutions_discussed = handle_challenges_solutions(
                challenges_faced=challenges_faced, solutions_discussed=solutions_discussed, profile=profile,
                messages=messages
            )

        logger.info(f"language used: %s", language)
        if language != 'en':
            voice_transliterate_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.Transliterate, language=language
            ).first()
            if user_name and user_name != '':
                user_name = transliterate_text(
                    voice_provider=voice_transliterate_provider, message_body=user_name, target_language=language,
                    source_language='en'
                )
                user_name=get_transliteration_output(data=user_name)
            if organization and organization != '':
                organization = transliterate_text(
                    voice_provider=voice_transliterate_provider, message_body=organization, target_language=language,
                    source_language='en'
                )
                organization = get_transliteration_output(data=organization)
            title = translate_field(
                voice_provider=voice_provider, message_body=title, target_language=language
            )
            if isinstance(challenges_faced, str):
                challenges_faced = json_repair.repair_json(challenges_faced, return_objects=True)

            challenges_faced = [
                translate_field(
                    voice_provider=voice_provider,
                    message_body=challenge,
                    target_language=language
                )
                for challenge in challenges_faced
            ]

            if isinstance(solutions_discussed, str):
                solutions_discussed = json_repair.repair_json(solutions_discussed, return_objects=True)

            solutions_discussed = [
                translate_field(
                    voice_provider=voice_provider,
                    message_body=solution,
                    target_language=language
                )
                for solution in solutions_discussed
            ]

        if profile:
            address = ProfileAddress.objects.filter(profile=profile).first()
            if address:
                location_parts = filter(None, [address.block, address.district, address.state])
                location = ", ".join(location_parts)
            else:
                location = ""
        else:
            location = ""

        other_params = {
            'challenges_faced': challenges_faced,
            'solutions_discussed': solutions_discussed,
            'user_name': user_name,
            'location': user_location,
            'organization': organization,
            'participants_count': participants_count,
            'discussion_date': discussion_date,
            'flow': flow
        }

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = title
            story.other_params = other_params
            story.stage = StoryStatusChoices.COMPLETED
            story.location = location
            story.validation_logs = combined_reason
        else:
            story = Story(
                title=title,
                author=profile,
                session=session,
                stage=StoryStatusChoices.COMPLETED,
                location=location,
                validation_logs=combined_reason,
                language=language,
                other_params=other_params
            )
        story.save()

        return story, None
    except Exception as e:
        logger.error('Error Occured: %s', e, exc_info=True)
        traceback.print_exc()
        raise Exception("Failed to save chaupal report")


def get_transliteration_output(data):
    if data and isinstance(data, dict):
        data = data.get('content', [])
    if data and isinstance(data, list) and len(data) > 0:
        return data[0]

    return None


def save_ptm_story(
        response_json_story, language, voice_provider, profile, session, combined_reason, flow=None,
        company_bot=None
):
    try:
        name = response_json_story.get("name", "")
        district = response_json_story.get("district", "")
        school = response_json_story.get("school", "")
        role = response_json_story.get("role", "")
        ptm_experience_summary = response_json_story.get("ptm_experience_summary", "")
        key_highlights = response_json_story.get("key_highlights", "")
        perceived_changes_or_impact = response_json_story.get("perceived_changes_or_impact", "")

        # if language != "en":
        #     ptm_experience_summary = translate_field(voice_provider, ptm_experience_summary, target_language=language)
        #     key_highlights = translate_field(voice_provider, key_highlights, target_language=language)
        #     expected_impact = translate_field(voice_provider, expected_impact, target_language=language)
        #
        #     voice_transliterate_provider = Voice.objects.filter(
        #         company_bot=company_bot, type=VoiceType.Transliterate, language=language
        #     ).first()
        #
        #     if name and name != '':
        #         is_sentence = ' ' in name
        #         name = transliterate_text(
        #             voice_provider=voice_transliterate_provider, message_body=name, target_language=language,
        #             source_language='en',
        #             is_sentence=is_sentence
        #         )
        #         name = get_transliteration_output(data=name)
        #
        #     name = translate_field(voice_provider, name, target_language=language)
        #     district = translate_field(voice_provider, district, target_language=language)
        #     school = translate_field(voice_provider, school, target_language=language)
        #     role = translate_field(voice_provider, role, target_language=language)

        other_params = {
            "user_name": name,
            "district": district,
            "school": school,
            "role": role,
            "ptm_experience_summary": ptm_experience_summary,
            "key_highlights": key_highlights,
            "perceived_changes_or_impact": perceived_changes_or_impact,
            "flow": flow,
        }

        title = f"{name}'s PTM Reflection" if name and name != '' else "PTM Reflection"

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = title
            story.language = language
            story.stage = StoryStatusChoices.COMPLETED
            story.other_params = other_params
            story.validation_logs = combined_reason
        else:
            story = Story(
                title=title,
                author=profile,
                session=session,
                language=language,
                stage=StoryStatusChoices.COMPLETED,
                other_params=other_params,
                validation_logs=combined_reason
            )
        story.save()
        return story, ptm_experience_summary
    except Exception as e:
        logger.error("Error in save_ptm_story: %s", e, exc_info=True)
        traceback.print_exc()
        raise Exception("Failed to save PTM story")



async def validate_story_llm(formatted_content_prompt, formatted_story_prompt, messages, tool_content, tool_story,
                             company_bot, flow):
    async def func1():
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            return await asyncio.to_thread(
                functools.partial(
                    handle_bedrock_model,
                    system_prompt=formatted_content_prompt,
                    messages=messages,
                    tools=tool_content,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    top_p=company_bot.filter_score,
                    model_name=company_bot.llm_model,
                    company_bot=company_bot
                )
            )


    async def func2():
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            return await asyncio.to_thread(
                functools.partial(
                    handle_bedrock_model,
                    system_prompt=formatted_story_prompt,
                    messages=messages,
                    tools=tool_story,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    top_p=company_bot.filter_score,
                    model_name=company_bot.llm_model,
                    company_bot=company_bot
                )
            )



    if flow in [SessionFlowName.LoginMiStory, SessionFlowName.GuestMiStory, SessionFlowName.Reflection,
                SessionFlowName.megaPTM, SessionFlowName.SsoFlow
    ]:
        response_json_content, response_json_story = await asyncio.gather(func1(), func2())
    else:
        response_json_content = await func1()
        response_json_story = None
    logger.info(f"Validation: response_json_content: %s", response_json_content)
    logger.info(f"Validation: response_json_story: %s", response_json_story)
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        for response in [response_json_content, response_json_story]:
            if response and isinstance(response, dict):
                extracted_data = response.pop("parameters", response.pop("input", None))
                if extracted_data and isinstance(extracted_data, dict):
                    response.clear()
                    response.update(extracted_data)

    elif company_bot.provider == LLMProvider.OPENAI:
        pass
    reason_content=""
    reason_content = response_json_content.get('reason')
    response_json_content = response_json_content.get('final_answer')
    if response_json_content and isinstance(response_json_content, str):
        response_json_content = json_repair.repair_json(response_json_content, return_objects=True)

    reason_story=""
    if response_json_story:
        reason_story = response_json_story.get('reason')
        response_json_story = response_json_story.get('final_answer')
    if response_json_story and isinstance(response_json_story, str):
        response_json_story = json_repair.repair_json(response_json_story, return_objects=True)

    logger.info(f"Final Validation: response_json_content: %s", response_json_content)
    logger.info(f"Final Validation: response_json_story: %s", response_json_story)

    if (isinstance(response_json_story, dict) and response_json_story.get("type") and
            "value" in response_json_story):
        value = response_json_story.get("value")
        if isinstance(value, str) and value.strip():
            value = json_repair.repair_json(value, return_objects=True)
        response_json_story = value

    if (isinstance(response_json_content, dict) and response_json_content.get("type") and
            "value" in response_json_content):
        value = response_json_content.get("value")
        if isinstance(value, str) and value.strip():
            value = json_repair.repair_json(value, return_objects=True)
        response_json_content = value

    combined_result = {**(response_json_content or {}), **(response_json_story or {})}

    combined_reason = {
        "reason_content": reason_content,
        "reason_story": reason_story
    }

    return combined_result, combined_reason


def retry_if_result_none(result):
    return result is None