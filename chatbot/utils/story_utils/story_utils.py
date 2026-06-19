from pygments.lexer import combined

from chatbot.models import (Profile, CompanyChat, ChatSession, ChatStatus, Voice, VoiceType, SessionFlowName, BotVernacular, StoryTranslation, CompanyBot)
from chatbot.models.company_models import Flow
from chatbot.serializer.profile_serializer import ProfileSerializer
from chatbot.utils.chat_utils import get_guided_chat
from chatbot.utils.shikshalokam_mitra_utils import get_stored_conversation, get_stored_chathistory
from chatbot.utils.shikshalokam_story_utils import save_shikshalokam_story, save_project_story
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.story_utils.common.generic_story_tasks import save_generic_story
from chatbot.utils.story_utils.get_story_prompts import get_creation_promt, get_tool_values, get_validation_prompt
from chatbot.utils.story_utils.story_llm import generate_story_llm, validate_story_llm
from rest_framework.exceptions import NotFound

from chatbot.utils.story_utils.chaupal.chaupal_story_tasks import save_chaupal_report
from chatbot.utils.story_utils.format_utils import get_formatted_story
from chatbot.utils.story_utils.mi_story_capture.mi_story_tasks import save_story
from chatbot.utils.story_utils.ptm.ptm_story_tasks import save_ptm_story

import asyncio
import logging
import traceback
from pprint import pprint

logger = logging.getLogger('django')


def create_story_object(profile_id, session, access_token, flow, language='en'):
    voice_provider = None
    company_bot = None
    print("Working with flow: ", flow)
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

        pprint({
            "formatted_content_prompt": formatted_content_prompt,
            "formatted_story_prompt": formatted_story_prompt,
            "tag_context": tag_context,
            "project_data": project_data,
        })

        intro_to_pass = None

        if flow in [SessionFlowName.GuestMiStory, SessionFlowName.GuestDiscussion]:
            route_to_use = None
            if flow == SessionFlowName.GuestMiStory:
                route_to_use = '/guided_guest'
            elif flow == SessionFlowName.GuestDiscussion:
                route_to_use = '/shikshalokam_chaupal'
            if route_to_use:
                flow_company_bot = CompanyBot.objects.get(company=profile.company, route=route_to_use)
                bot_vernacular = BotVernacular.objects.filter(company_bot=flow_company_bot).first()
                if bot_vernacular:
                    if access_token:
                        intro_to_pass = bot_vernacular.introductory_message
                        if profile and profile.first_name and intro_to_pass:
                            words = intro_to_pass.split(" ", 1)
                            if len(words) > 1:
                                intro_to_pass = f"{words[0]} {profile.first_name} {words[1]}"
                            else:
                                intro_to_pass = f"{words[0]} {profile.first_name}"
                    else:
                        intro_to_pass = bot_vernacular.alt_introductory_message
        # Handle intro for new flows (common flow)
        else:
            try:
                session_company_bot = chat_session.company_bot
                if session_company_bot:
                    bot_vernacular = BotVernacular.objects.filter(company_bot=session_company_bot).first()
                    if bot_vernacular:
                        if access_token:
                            intro_to_pass = bot_vernacular.introductory_message
                            if profile and profile.first_name and intro_to_pass:
                                words = intro_to_pass.split(" ", 1)
                                if len(words) > 1:
                                    intro_to_pass = f"{words[0]} {profile.first_name} {words[1]}"
                                else:
                                    intro_to_pass = f"{words[0]} {profile.first_name}"
                        else:
                            intro_to_pass = bot_vernacular.alt_introductory_message
            except Exception as e:
                logger.warning(f"Could not get intro for new flow {flow}: {e}")

        messages = get_guided_chat(
            company_bot=company_bot, company_chats=company_chats, intro=intro_to_pass
        )

        tool_content, tool_story = get_tool_values(company_bot=company_bot)

        response_json_content, response_json_story = asyncio.run(
            generate_story_llm(
                formatted_content_prompt=formatted_content_prompt, formatted_story_prompt=formatted_story_prompt,
                messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=company_bot,
            )
        )

        logger.info(f"STORY response_json_content: %s", response_json_content)
        logger.info(f"STORY response_json_story: %s", response_json_story)

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

        logger.info(f"VALIDATION STORY response_json_story: %s", response_json_story)

        # Save story based on flow type
        if flow in [SessionFlowName.LoginMiStory, SessionFlowName.SsoFlow, SessionFlowName.GuestMiStory,
                    SessionFlowName.Reflection]:
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
        elif flow == SessionFlowName.GuestDiscussion:
            story, problem_statement = save_chaupal_report(
                response_json_story=response_json_story, language=language, voice_provider=voice_provider,
                profile=profile, session=session, combined_reason=combined_reason, flow=flow,
                messages=messages, company_bot=company_bot
            )
        else:
            story, problem_statement = save_generic_story(
                response_json_story=response_json_story, language=language, voice_provider=voice_provider,
                profile=profile, session=session, combined_reason=combined_reason, flow=flow,
                project_id=chat_session.project_id, company_bot=company_bot
            )

        if story:
            formatted_content = get_formatted_story(story)
            if formatted_content:
                story.formatted_content = formatted_content
                story.save(update_fields=['formatted_content'])

            if language != 'en':
                try:
                    translation = story.translations.get(language=language)
                    formatted_translation_content = get_formatted_story(translation)
                    if formatted_translation_content:
                        translation.formatted_content = formatted_translation_content
                        translation.save(update_fields=['formatted_content'])
                except StoryTranslation.DoesNotExist:
                    pass

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

        return story_id, story_content, "", ""

    except Exception as e:
        traceback.print_exc()

        error_type = getattr(e, "code", "generic_error")

        if not company_bot:
            profile = Profile.objects.filter(id=profile_id).first()
            company_bot, validate_bot = get_story_company_bot(profile=profile, flow=flow)

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = get_bot_error_message(bot_vernacular, error_type)
        if voice_provider and language != 'en':
            error_message = translate_field(
                voice_provider=voice_provider, message_body=error_message, target_language=language
            )
        return "", "", error_message, error_type


def get_bot_error_message(bot_vernacular, error_type):

    if not bot_vernacular or not bot_vernacular.error_message:
        return "Please try again!"

    raw = bot_vernacular.error_message

    if isinstance(raw, dict):
        data = raw
    else:
        try:
            import json
            data = json.loads(raw)
        except Exception:
            return raw

    return data.get(error_type) or data.get("generic_error") or "Please try again!"


def generate_story(profile_id, session, access_token, flow, language='en'):
    voice_provider = None
    company_bot = None
    print("Working with flow: ", flow)
    try:
        profile = Profile.objects.prefetch_related('profile_address').defer('password').get(id=profile_id)

        profile_data = ProfileSerializer(profile).data
        company_chats = CompanyChat.objects.select_related('sender', 'receiver').filter(session=session).order_by('created_at').values("receiver", "receiver__id", "translated_message", "message", "status", "created_at")

        company_bot, validate_bot = get_story_company_bot_simple(flow=flow)

        voice_provider = Voice.objects.filter(company_bot=company_bot, type=VoiceType.TextToText, language=language).first()

        chat_session = ChatSession.objects.get(session=session)

        formatted_content_prompt, formatted_story_prompt, tag_context, project_data = get_creation_promt(company_bot=company_bot, profile=profile_data)

        intro_to_pass = None

        try:
            session_company_bot = chat_session.company_bot
            if session_company_bot:
                bot_vernacular = BotVernacular.objects.filter(company_bot=session_company_bot).first()
                if bot_vernacular:
                    if access_token:
                        intro_to_pass = bot_vernacular.introductory_message
                        if profile_data and profile_data.get("first_name") and intro_to_pass:
                            words = intro_to_pass.split(" ", 1)
                            if len(words) > 1:
                                intro_to_pass = f"{words[0]} {profile_data.get('first_name')} {words[1]}"
                            else:
                                intro_to_pass = f"{words[0]} {profile_data.get('first_name')}"
                    else:
                        intro_to_pass = bot_vernacular.alt_introductory_message
            else:
                raise ValueError("No bot found in the chat session")
        except Exception as e:
            traceback.print_exc()
            logger.warning(f"Could not get intro for new flow {flow}: {e}")

        messages = get_guided_chat(
            company_bot=company_bot, company_chats=company_chats, intro=intro_to_pass
        )

        tool_content, tool_story = get_tool_values(company_bot=company_bot)

        response_json_content, response_json_story = asyncio.run(
            generate_story_llm(
                formatted_content_prompt=formatted_content_prompt, formatted_story_prompt=formatted_story_prompt,
                messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=company_bot
            )
        )

        logger.info(f"STORY response_json_content: %s", response_json_content)
        logger.info(f"STORY response_json_story: %s", response_json_story)

        combined_reason = None
        if validate_bot:
            validate_content_prompt, validate_story_prompt = get_validation_prompt(
                response_json_story=response_json_story, validate_bot=validate_bot,
                response_json_content=response_json_content, tag_context=tag_context, project_data=project_data,
                profile=profile_data
            )

            tool_content, tool_story = get_tool_values(company_bot=validate_bot)

            if company_bot.provider != validate_bot.provider:
                messages = get_guided_chat(company_bot=validate_bot, company_chats=company_chats, intro=intro_to_pass)

            response_json_story, combined_reason = asyncio.run(
                validate_story_llm(
                    formatted_content_prompt=validate_content_prompt, formatted_story_prompt=validate_story_prompt,
                    messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=validate_bot,
                    flow=flow
                )
            )

        logger.info("VALIDATION STORY response_json_story: {story}".format(story=response_json_story))

        story, problem_statement = save_generic_story(
            response_json_story=response_json_story, language=language, voice_provider=voice_provider,
            profile=profile_data, session=session, combined_reason=combined_reason, flow=flow,
             company_bot=company_bot
        )

        if story:
            formatted_content = get_formatted_story(story)
            if formatted_content:
                story.formatted_content = formatted_content
                story.save(update_fields=['formatted_content'])

            if language != 'en':
                try:
                    translation = story.translations.get(language=language)
                    formatted_translation_content = get_formatted_story(translation)
                    if formatted_translation_content:
                        translation.formatted_content = formatted_translation_content
                        translation.save(update_fields=['formatted_content'])
                except StoryTranslation.DoesNotExist:
                    pass

        chat_session.session_status = ChatStatus.COMPLETED
        chat_session.save(update_fields=['session_status'])
        chat_session.save_title(language=language)

        if flow == SessionFlowName.Reflection:
            conversation = get_stored_conversation(company_chats=company_chats)
            chat_history = get_stored_chathistory(company_chats=company_chats)
        else:
            conversation, chat_history = [], []

        save_project_story(
            story=story, profile=profile_data,
            problem_statement=problem_statement, chat_history=chat_history, access_token=access_token,
            project_id=None, session=session, conversation=conversation, flow=flow
        )

        story_id = story.id if story and story.id else ""
        story_content = story.content if story and story.content else ""

        return story_id, story_content, "", ""

    except Exception as e:
        traceback.print_exc()
        error_type = getattr(e, "code", "generic_error")

        if not company_bot:
            profile = Profile.objects.filter(id=profile_id).first()
            company_bot, validate_bot = get_story_company_bot_simple(flow=flow)

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = get_bot_error_message(bot_vernacular, error_type)

        if voice_provider and language != 'en':
            error_message = translate_field(
                voice_provider=voice_provider, message_body=error_message, target_language=language
            )
        return "", "", error_message, error_type


def get_story_company_bot_simple(flow):
    try:
        company_flow = Flow.objects.get(flow_route=flow)

        company_story_bot = company_flow.story_bot
        company_story_validation_bot = company_flow.story_validation_bot

        if not company_story_bot:
            raise NotFound(detail=f"Story bot not configured for the flow: {flow}")

        return company_story_bot, company_story_validation_bot

    except Flow.DoesNotExist:
        logger.error(f"Flow not found for route: {flow}")
        raise NotFound(detail=f"Flow not found with route: {flow}")



def get_story_company_bot(profile, flow):
    if flow in [SessionFlowName.LoginMiStory, SessionFlowName.Reflection, SessionFlowName.SsoFlow]:
        company_bot = CompanyBot.objects.get(route='/story')
        validate_bot = CompanyBot.objects.get(route='/story_validation')
    elif flow in [SessionFlowName.GuestMiStory]:
        company_bot = CompanyBot.objects.get(route='/guest-story')
        validate_bot = CompanyBot.objects.get(route='/guest-story_validation')
    elif flow in [SessionFlowName.megaPTM]:
        company_bot = CompanyBot.objects.get(route='/ptm-story')
        validate_bot = CompanyBot.objects.get(route='/ptm-story_validation')
    elif flow == SessionFlowName.GuestDiscussion:
        company_bot = CompanyBot.objects.get(route='/chaupal-story')
        validate_bot = CompanyBot.objects.get(route='/chaupal-_validation')
    else:
        flow_name = flow.value if hasattr(flow, 'value') else str(flow)
        story_route = f'/{flow_name}-story'
        validation_route = f'/{flow_name}-story_validation'

        try:
            company_bot = CompanyBot.objects.get(route=story_route)
            validate_bot = CompanyBot.objects.get(route=validation_route)
        except CompanyBot.DoesNotExist:
            logger.error(f"CompanyBot not found for routes: {story_route}, {validation_route}")
            company_bot = CompanyBot.objects.get(route='/story')
            validate_bot = CompanyBot.objects.get(route='/story_validation')

    return company_bot, validate_bot