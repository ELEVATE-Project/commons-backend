from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import ChatSession, CompanyBot, CompanyChat, Story, ChatStatus
from chatbot.models.enums import LLMProvider, StoryStatusChoices
from datetime import timedelta
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
import logging


logger = logging.getLogger('django')

SHIKSHA_SAMVAD_SESSION_TYPE = 'shiksha-samvad'
SHIKSHA_SAMVAD_BOT_ROUTE = '/story-creation-shikshasamvad'
STORY_LLM_MAX_ATTEMPTS = 3


def _story_response_has_title(response):
    """True if the LLM returned a dict with a non-empty title."""
    if not isinstance(response, dict):
        return False
    title = response.get('title')
    return title is not None and str(title).strip() != ''


def chat_sessions_without_story(session_type=SHIKSHA_SAMVAD_SESSION_TYPE):
    """
    ChatSession rows with session_status COMPLETED that have no Story with the same
    `session` string (Story links via Story.session, not a FK on ChatSession).
    Pass session_type=None to include all session types.
    """
    linked_story = Story.objects.filter(session=OuterRef('session'))
    half_hour_ago = timezone.now() - timedelta(minutes=30)
    qs = ChatSession.objects.filter(
        ~Exists(linked_story),
        session_type=session_type,
    ).filter(
        Q(created_at__lte=half_hour_ago)
        | Q(created_at__gte=half_hour_ago, session_status=ChatStatus.COMPLETED)
    )
    return qs


def chat_session_ids_without_story(session_type=SHIKSHA_SAMVAD_SESSION_TYPE):
    """`session` values (string ids) for ChatSessions that have no matching Story."""
    return chat_sessions_without_story(session_type=session_type).values_list('session', flat=True)


def _build_chat_transcript(company_chats):
    transcript_parts = []
    question_index = 0
    answer_index = 0
    for chat in company_chats:
        if chat.sender_id == 1:
            question_index += 1
            message = chat.message
            if chat.translated_message is not None and chat.translated_message != '':
                message = chat.translated_message
            transcript_parts.append(
                f"<question_{question_index}>\n{message}\n</question_{question_index}>"
            )
        else:
            answer_index += 1
            message = chat.message
            if chat.translated_message is not None and chat.translated_message != '':
                message = chat.translated_message
            transcript_parts.append(
                f"<answer_{answer_index}>\n{message}\n</answer_{answer_index}>"
            )
    return '\n'.join(transcript_parts)


def _build_messages(company_bot, company_chats):
    transcript = _build_chat_transcript(company_chats=company_chats)
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        return [
            {
                'role': 'user',
                'content': [{'text': transcript}]
            },
            {
                'role': 'assistant',
                'content': [{'text': "```json"}]
            }
        ]
    return [{
        'role': 'user',
        'content': transcript
    }]


def _get_system_prompt(company_bot):
    prompt_parts = [company_bot.context, company_bot.end_context]
    prompt_text = '\n\n'.join([part for part in prompt_parts if part and part.strip()])
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        return [{'text': prompt_text}] if prompt_text else None
    return prompt_text


def _call_story_llm(company_bot, messages, system_prompt):
    """Single LLM invocation for story JSON (no retries)."""
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        print("messages: ", messages)
        print("system_prompt: ", system_prompt)
        return handle_bedrock_model(
            company_bot=company_bot,
            system_prompt=system_prompt,
            messages=messages,
            max_token=company_bot.max_token,
            temperature=company_bot.bot_temperature,
            top_p=company_bot.filter_score,
            model_name=company_bot.llm_model,
            is_json_response=False,
            stop_sequences=["```"],
        )

    openai_messages = messages
    if system_prompt:
        openai_messages = [{'role': 'system', 'content': system_prompt}] + messages
    return handle_openai_model(
        company_bot=company_bot,
        messages=openai_messages,
        max_token=company_bot.max_token,
        temperature=company_bot.bot_temperature,
        model_name=company_bot.llm_model,
        top_p=company_bot.filter_score,
        is_json_response=False,
        key_name=company_bot.llm_key or 'OPENAI_API_KEY',
        is_actual_key=bool(company_bot.provider_keys),
    )


def _generate_story_for_session(company_bot, session):
    company_chats = CompanyChat.objects.filter(session=session).order_by('created_at')
    if not company_chats.exists():
        logger.info('No chats found for session=%s', session)
        return None

    messages = _build_messages(company_bot=company_bot, company_chats=company_chats)
    system_prompt = _get_system_prompt(company_bot)

    if company_bot.provider not in (
        LLMProvider.BEDROCK_CONVERSE,
        LLMProvider.OPENAI,
    ):
        logger.warning('Unsupported provider=%s for bot=%s', company_bot.provider, company_bot.id)
        return None

    for attempt in range(1, STORY_LLM_MAX_ATTEMPTS + 1):
        try:
            response = _call_story_llm(company_bot, messages, system_prompt)
        except Exception as e:
            log_fn = logger.error if attempt == STORY_LLM_MAX_ATTEMPTS else logger.warning
            log_fn(
                'Story LLM call failed session=%s attempt=%s/%s: %s',
                session,
                attempt,
                STORY_LLM_MAX_ATTEMPTS,
                e,
                exc_info=(attempt == STORY_LLM_MAX_ATTEMPTS),
            )
            continue

        if _story_response_has_title(response):
            return response

        logger.warning(
            'Story LLM missing or empty title session=%s attempt=%s/%s response=%s',
            session,
            attempt,
            STORY_LLM_MAX_ATTEMPTS,
            response,
        )

    return None


def _persist_story_from_llm_response(session_id, response):
    """
    Save LLM story JSON: title on Story.title, remaining keys in Story.other_params,
    session id on Story.session, author from ChatSession.profile when present.
    """
    title = str(response['title']).strip()
    other_params = {k: v for k, v in response.items() if k != 'title'}
    chat_session = (
        ChatSession.objects.filter(session=session_id)
        .select_related('profile')
        .first()
    )
    author = chat_session.profile if chat_session else None
    return Story.objects.create(
        session=session_id,
        title=title,
        other_params=other_params,
        author=author,
        stage=StoryStatusChoices.COMPLETED
    )


def create_story():
    try:
        company_bot = CompanyBot.objects.filter(route=SHIKSHA_SAMVAD_BOT_ROUTE).first()
        if not company_bot:
            logger.error('No CompanyBot found for route=%s', SHIKSHA_SAMVAD_BOT_ROUTE)
            return

        shiksha_samvad_session_for_story = ChatSession.objects.filter(
            session=OuterRef('session'),
            session_type=SHIKSHA_SAMVAD_SESSION_TYPE,
        )
        matching_stories = Story.objects.filter(Exists(shiksha_samvad_session_for_story))

        sessions_missing_story = chat_sessions_without_story()

        logger.info(
            'Creating story for Shiksha Samvad (%s stories, %s chat sessions without story)',
            matching_stories.count(),
            sessions_missing_story.count(),
        )
        for session in sessions_missing_story.values_list('session', flat=True):
            response = _generate_story_for_session(company_bot=company_bot, session=session)

            if response is None:
                logger.error(
                    'No valid story after %s LLM attempts for session=%s',
                    STORY_LLM_MAX_ATTEMPTS,
                    session,
                )
                continue

            story = _persist_story_from_llm_response(session_id=session, response=response)
            logger.info(
                'Created story id=%s session=%s route=%s title=%s other_params_keys=%s',
                story.id,
                session,
                SHIKSHA_SAMVAD_BOT_ROUTE,
                story.title,
                list(story.other_params.keys()) if story.other_params else [],
            )

    except Exception as e:
        logger.error('Error creating story for Shiksha Samvad: %s', e)