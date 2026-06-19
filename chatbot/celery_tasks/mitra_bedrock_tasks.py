import traceback
from celery import shared_task
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.celery_tasks.handle_message import translate_and_send_message
from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.models import CompanyChat, Profile, CompanyBot, ChatStatus, BotVernacular, Voice, VoiceType
import json_repair

from chatbot.utils.story_llama_utils import translate_field


@shared_task
def get_mitra_bedrock_response(channel_name, session_id, profile_id, route):
    print(session_id)
    try:
        company_chats = CompanyChat.objects.filter(session=session_id).order_by('created_at')
        profile = Profile.objects.filter(id=profile_id).first()
        ai_user = Profile.objects.get(id=1)
        company_bot = CompanyBot.objects.get(route='/mitra-create')
        system_context = company_bot.context

        prompt_to_use = [
            {
                'text': system_context.replace("{first_name}", profile.first_name if profile else "")
            }
        ]

        messages=[]
        for chat in company_chats:
            if chat.receiver == ai_user:
                user_message = chat.message
                if chat.translated_message is not None and chat.translated_message != '':
                    user_message = chat.translated_message
                messages.append({
                    'role': 'user',
                    'content': [{'text': user_message}]
                })
            else:
                messages.append({
                    'role': 'assistant',
                    "content": [{'text': chat.message}]
                })

        tool_content = company_bot.tool_context
        if tool_content and isinstance(tool_content, str):
            tool_content = json_repair.repair_json(tool_content, return_objects=True)
        try:
            response = handle_bedrock_model(
                system_prompt=prompt_to_use, messages=messages, is_json_response=True,
                model_name=company_bot.llm_model, temperature=company_bot.bot_temperature,
                max_token=company_bot.max_token, company_bot=company_bot
            )
            message = response.get("message", "")
            if message == '' and  response.get("should_move_forward") == 'no':
                raise
        except Exception:
            bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=route).first()
            error_message = bot_vernacular.error_message if bot_vernacular.error_message else "Please try again!"
            translated_message = translate_and_send_message(
                accumulated_message=error_message, current_channel_name=channel_name,
                current_step_number=1, finish_reason="stop", route=route,
                company_bot=company_bot
            )
            return translated_message

        print("response_body bedrock: ", response)

        if response:
            problem_statement = response.get("problem_statement", "")
            if route != 'en' and problem_statement and problem_statement != '':
                voice_provider = Voice.objects.filter(
                    company_bot=company_bot, type=VoiceType.TextToText, language=route
                ).first()
                problem_statement = translate_field(
                    voice_provider=voice_provider, message_body=problem_statement, target_language=route,
                    source_language='en'
                )

            extra_content = {
                "problem_statement": problem_statement,
                "should_move_forward": response.get("should_move_forward", 'no'),
                "validation": response.get("validation", "")
            }
            end_context = company_bot.end_context
            end_context = json_repair.repair_json(end_context, return_objects=True)

            if response.get("should_move_forward") == 'yes':
                message = ''
            elif response.get("validation") == 'NO_PROBLEM_STATEMENT':
                message = end_context.get('NO_PROBLEM_STATEMENT', message)
            elif response.get("validation") == 'OUT_OF_SCOPE':
                message = end_context.get('OUT_OF_SCOPE', message)

            translated_message = translate_and_send_message(
                accumulated_message=message, current_channel_name=channel_name,
                current_step_number=1, finish_reason="stop", route=route,
                extra_content=extra_content, company_bot=company_bot
            )
            if not message or not str(message).strip():
                message = "Understood."

            save_in_company_db(
                session_id, profile_id, 'AI', message, None, ChatStatus.IN_PROGRESS,
                translated_message
            )
        return response
    except Exception as e:
        print(e)
        traceback.print_exc()
