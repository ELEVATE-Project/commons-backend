from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import CompanyBot, LLMProvider
from chatbot.utils.chat_utils import get_guided_chat
from chatbot.utils.shiksha_chaupal.base_utils import get_guided_prompt
import logging
from dateutil import parser
from datetime import datetime
import pytz
import json_repair


logger = logging.getLogger('django')
INDIA_TZ = pytz.timezone("Asia/Kolkata")


def handle_date_prompt(intro_mssg, profile, company_chats, other_info):
    bot_question = None

    if profile:
        company_bot = CompanyBot.objects.get(company=profile.company, route='/date-validator')
    else:
        company_bot = CompanyBot.objects.get(route='/date-validator')

    prompt_to_use = get_guided_prompt(
        company_bot=company_bot, system_context=company_bot.context
    )

    messages = get_guided_chat(
        company_bot=company_bot, company_chats=company_chats
    )

    response = None
    try:
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            response = handle_bedrock_model(
                system_prompt=prompt_to_use, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot
            )
        elif company_bot.provider == LLMProvider.OPENAI:
            response = handle_openai_model(
                system_prompt=prompt_to_use, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
                is_json_response=True
            )
    except Exception as e:
        logger.error(f"Error in handle_date_prompt: {e}")
        response = None

    if not response:
        return "I am sorry, I could not understand completely. Could you rephrase this please?"

    date_type, user_date = interpret_date_response(response)
    logger.info(f"date_type: %s", date_type)

    try:
        last_ai_message = company_chats.filter(receiver__id=1).order_by('-created_at').first()
        if last_ai_message:
            last_ai_message.translated_message = user_date
            last_ai_message.save()
            logger.info(f"Updated last AI message with user_date: %s", user_date)
    except Exception as e:
        logger.error(f"Error updating translated_message: {e}")

    end_context = json_repair.repair_json(company_bot.end_context, return_objects=True)

    if end_context:
        bot_question = end_context.get(date_type, None)

    return bot_question


def interpret_date_response(date_response):
    if date_response and isinstance(date_response, str):
        date_response = json_repair.repair_json(date_response, return_objects=True)

    if date_response and isinstance(date_response, dict):
        if (isinstance(date_response, dict) and date_response.get("type") and
                "value" in date_response):
            value = date_response.get("value")
            if isinstance(value, str) and value.strip():
                value = json_repair.repair_json(value, return_objects=True)
            date_response = value
    user_date = date_response.get("parsed_date", '')
    logger.info(f"user_date: %s", user_date)
    try:
        parsed_date = parser.parse(user_date, dayfirst=True)
        logger.info(f"parsed_date: %s", parsed_date)
        today = datetime.now(INDIA_TZ).date()
        logger.info(f"today: %s", today)

        normalized_user_date = user_date.lower()
        logger.info(f"normalized_user_date date: %s", normalized_user_date)

        if parsed_date.year == today.year and str(today.year) not in normalized_user_date:
            return "PHRASE", user_date
        if (parsed_date.month == today.month and
                str(parsed_date.month) not in normalized_user_date and
                parsed_date.strftime('%B').lower() not in normalized_user_date and
                parsed_date.strftime('%b').lower() not in normalized_user_date):
            return "PHRASE"

        if parsed_date.day == today.day and str(parsed_date.day) not in normalized_user_date:
            return "PHRASE", user_date

        if parsed_date.date() > today:
            return "FUTURE_DATE", user_date
        elif parsed_date.date() == today:
            return "PAST_DATE", user_date
        else:
            return "PAST_DATE", user_date

    except Exception:
        return "PHRASE", user_date
