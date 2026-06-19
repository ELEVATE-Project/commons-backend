import json
from chatbot.llm_models.llm_script import handle_openai_model, handle_bedrock_model
from chatbot.models import LLMProvider
import json_repair
import logging


logger = logging.getLogger('django')

def handle_custom_translation(company_bot, message_body, source_language, target_language):

    try:
        if company_bot and company_bot.provider == LLMProvider.OPENAI:
            messages = [
                {
                    'role': 'user',
                    'content': message_body
                }
            ]

            context = company_bot.context or ""
            context += f"\nSource language: {source_language}\nTarget language: {target_language}"
            context += f"\n{company_bot.end_context}" if company_bot.end_context else ""
            system_prompt = [{"role": "system", "content": context}]

            tools = None
            tool_choice = None
            try:
                tool_context = json_repair.repair_json(company_bot.tool_context, return_objects=True)
                if tool_context:
                    tools = tool_context.get("tool")
                    tool_choice = tool_context.get("tool_choice", "auto")

                logger.info("Using bot tool_context")
            except Exception as e:
                logger.error(f"Failed to parse bot tool_context: {e}")

            logger.info("-----------------OPENAI OBJECTIVES---------------------------------", )
            logger.info(f"openai system_prompt: {system_prompt}")
            logger.info(f"openai messages: {messages}")
            response = handle_openai_model(
                messages=messages, system_prompt=system_prompt, max_token=company_bot.max_token,
                temperature=company_bot.bot_temperature, company_bot=company_bot,
                top_p=company_bot.filter_score if company_bot.filter_score else None,
                tool_choice=tool_choice, tools=tools, stream=False, is_json_response=True
            )
        elif company_bot and company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            messages = [{
                'role': 'user',
                'content': [{'text': message_body}]
            }]

            context = company_bot.context or ""
            context += f"\nSource language: {source_language}\nTarget language: {target_language}"
            system_prompt = [
                {
                    'text': context
                }
            ]
            tool_context = company_bot.tool_context
            tool_context = json_repair.repair_json(tool_context, return_objects=True)

            response = handle_bedrock_model(
                system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
                tools=tool_context, top_p=company_bot.filter_score,
            )
        else:
            raise ValueError("Unsupported LLM provider")

        parsed_output = parse_llm_response(response)

        return {
            "status": 200,
            "content": parsed_output
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": 500,
            "content": message_body
        }

def parse_llm_response(response):
    print("llm response:", response)

    if isinstance(response, str):
        response = json.loads(response)

    if not isinstance(response, dict):
        raise ValueError("INVALID_LLM_RESPONSE")

    output = response.get("output")

    if not isinstance(output, str):
        raise ValueError("INVALID_OUTPUT_FORMAT")

    return output
