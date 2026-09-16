from channels.layers import get_channel_layer
from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import ChatSession, ChatStatus, LLMProvider, CompanyBot
import logging
from chatbot.utils.one_shot_utils import get_assistant_prompt


logger = logging.getLogger('django')
channel_layer = get_channel_layer()


def get_chaupal_challenge_response(messages):

    response = None
    company_bot = CompanyBot.objects.get(route='/chaupal_challenges')
    challenge_prompt = get_assistant_prompt(company_bot=company_bot, content_prompt=company_bot.context)

    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        try:
            response = handle_bedrock_model(
                system_prompt=challenge_prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot
            )
        except Exception as e:
            logger.error(f"Got Error: %s", e)
            print(f"Got Error: {e}")
            response = None
    elif company_bot.provider == LLMProvider.OPENAI:
        response = handle_openai_model(
            system_prompt=challenge_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
            is_json_response=False
        )

    print("response_body bedrock: ", response)

    return response


def get_chaupal_solution_response(messages):

    response = None
    company_bot = CompanyBot.objects.get(route='/chaupal_solutions')
    challenge_prompt = get_assistant_prompt(company_bot=company_bot, content_prompt=company_bot.context)

    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        try:
            response = handle_bedrock_model(
                system_prompt=challenge_prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot
            )
        except Exception as e:
            logger.error(f"Got Error: %s", e)
            print(f"Got Error: {e}")
            response = None
    elif company_bot.provider == LLMProvider.OPENAI:
        response = handle_openai_model(
            system_prompt=challenge_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
            is_json_response=False
        )

    print("response_body bedrock: ", response)

    return response
