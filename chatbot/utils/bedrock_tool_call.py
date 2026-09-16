from channels.layers import get_channel_layer
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.celery_tasks.handle_message import translate_and_send_message
from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import ChatSession, ChatStatus, CompanyChat, LLMProvider
from chatbot.models.company_models import CompanyStateMachine
import logging


logger = logging.getLogger('django')
channel_layer = get_channel_layer()


def get_bedrock_tool_call_response(
        system_prompt, messages, company_bot, session_id, channel_name, route, profile_id
):

    chat_session = ChatSession.objects.get(session=session_id)
    current_step = chat_session.current_step
    chunks = []

    response = None
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        try:
            response = handle_bedrock_model(
                system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot
            )
        except Exception as e:
            logger.error(f"Got Error: %s", e)
            print(f"Got Error: {e}")
            response = None
    elif company_bot.provider == LLMProvider.OPENAI:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_state_information",
                    "description": "Get the information of the state you want to be in.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "state_name": {
                                "type": "string",
                                "description": "Name of the next state provided in the context."
                            }
                        },
                        "required": ["state_name"]
                    }
                }
            }
        ]
        response = handle_openai_model(
            system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
            tools=tools, tool_choice='auto', is_json_response=False
        )

    print("response_body bedrock: ", response)
    if response is None:
        response = 'I am sorry, I could not understood completely. Could you rephrase this please?'

    print("Response: ", response)
    is_function_call = False
    if isinstance(response, dict):
        is_function_call = True
    elif isinstance(response, str):
        if 'get_state_information' in response:
            is_function_call = True
    print("is_function_call: ", is_function_call)
    if is_function_call:
        print("its func call")
        chat_session.current_step += 1
        chat_session.save()
        state_machine = CompanyStateMachine.objects.get(company_bot=company_bot, step=chat_session.current_step)
        bot_question = state_machine.bot_question

        translated_message = translate_and_send_message(
            accumulated_message=bot_question, current_channel_name=channel_name,
            current_step_number=chat_session.current_step, finish_reason="stop", route=route,
            company_bot=company_bot
        )

        name_machine = state_machine.name
        print("name_machine: ", name_machine)
        if state_machine.name == "APPRECIATION":
            chat_status = ChatStatus.COMPLETED
        else:
            chat_status = ChatStatus.IN_PROGRESS

        save_in_company_db(
            session_id=session_id, profile_id=profile_id, initiated_by='AI', message=bot_question,
            chunks=chunks, status=chat_status, translated_message=translated_message, stage=state_machine.name
        )
        return response
    else:
        state_machine = CompanyStateMachine.objects.get(company_bot=company_bot, step=chat_session.current_step)
        print("its not a  func call")
        translated_message = translate_and_send_message(
            accumulated_message=response, current_channel_name=channel_name,
            current_step_number=current_step, finish_reason="stop", route=route,
            company_bot=company_bot
        )
        save_in_company_db(
            session_id=session_id, profile_id=profile_id, initiated_by='AI', message=response,
            chunks=chunks, status=ChatStatus.IN_PROGRESS, translated_message=translated_message,
            stage=state_machine.name
        )

        return response
