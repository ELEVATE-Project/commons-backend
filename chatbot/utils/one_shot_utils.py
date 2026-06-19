import json_repair
from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import CompanyBot, LLMProvider
from jinja2 import Template
from chatbot.utils.chat_utils import get_guided_chat
import logging


logger = logging.getLogger('django')


def get_remaining_strands(messages, company_chats, oneshot_bot, profile, intro=None, other_info=None, extra_params=None):

    assistant_route = extra_params.get('assistant_route','/oneshot_assistant')
    validator_route = extra_params.get('validator_route','/oneshot_validator')
    if profile:
        company_bot = CompanyBot.objects.filter(company=profile.company, route=assistant_route).first()
        validate_bot = CompanyBot.objects.filter(company=profile.company, route=validator_route).first()
    else:
        company_bot = CompanyBot.objects.filter(route=assistant_route).first()
        validate_bot = CompanyBot.objects.filter(route=validator_route).first()

    tool = company_bot.tool_context
    if tool and isinstance(tool, str):
        tool = json_repair.repair_json(tool, return_objects=True)

    one_shot_prompt = get_assistant_prompt(company_bot=company_bot, content_prompt=company_bot.context)
    if oneshot_bot.provider != company_bot.provider:
        print("provider is not same so changing message!")
        messages = get_guided_chat(
            company_bot=company_bot, company_chats=company_chats, intro=intro, other_info=other_info
        )
    response = None
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        try:
            response = handle_bedrock_model(
                system_prompt=one_shot_prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, tools=tool,
                company_bot=company_bot
            )
        except Exception as e:
            logger.error(f"Got Error: %s", e)
            print(f"Got Error: {e}")
            response = None
    elif company_bot.provider == LLMProvider.OPENAI:
        # openai_tool = convert_llama_to_openai_tool(llama_tool_call=tool)
        response = handle_openai_model(
            system_prompt=one_shot_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
        )

    if response:
        if response.get('parameters'):
            response = response.get('parameters')
        elif response.get('input'):
            response = response.get('input')

    tool = validate_bot.tool_context
    if tool and isinstance(tool, str):
        tool = json_repair.repair_json(tool, return_objects=True)

    context_data = {
        "oneshot_assistant_response": response
    }
    template = Template(validate_bot.tag_context)
    tag_context = template.render(context_data)
    content_prompt = f"""
                {validate_bot.context}
                {tag_context}
            """
    one_shot_prompt = get_assistant_prompt(company_bot=company_bot, content_prompt=content_prompt)

    if oneshot_bot.provider != validate_bot.provider:
        messages = get_guided_chat(
            company_bot=validate_bot, company_chats=company_chats, intro=intro, other_info=other_info
        )
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        try:
            response = handle_bedrock_model(
                system_prompt=one_shot_prompt, messages=messages, model_name=validate_bot.llm_model,
                temperature=validate_bot.bot_temperature, max_token=validate_bot.max_token, tools=tool,
                company_bot=company_bot
            )
        except Exception as e:
            logger.error(f"Got Error: %s", e)
            print(f"Got Error: {e}")
            response = {
                "error": "I am sorry, I could not understood completely. Could you rephrase this please?"
            }
    elif company_bot.provider == LLMProvider.OPENAI:
        # openai_tool = convert_llama_to_openai_tool(llama_tool_call=tool)
        response = handle_openai_model(
            system_prompt=one_shot_prompt, messages=messages, model_name=validate_bot.llm_model,
            temperature=validate_bot.bot_temperature, max_token=validate_bot.max_token,
        )


    if response:
        if response.get('parameters'):
            response = response.get('parameters')
        elif response.get('input'):
            response = response.get('input')

    return response


def get_assistant_prompt(company_bot, content_prompt):
    prompt_to_use=[]
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        prompt_to_use = [
            {
                'text': content_prompt
            }
        ]
    elif company_bot.provider == LLMProvider.OPENAI:
        prompt_to_use = [
            {
                'role': 'system',
                'content': content_prompt
            }
        ]

    return prompt_to_use
