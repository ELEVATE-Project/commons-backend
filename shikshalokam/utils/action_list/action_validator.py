from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import LLMProvider
from shikshalokam.utils.action_list.action_parser import unwrap_tool_values
from shikshalokam.utils.chunks_utils import render_template_with_context
import logging
import json_repair

logger = logging.getLogger('django')


def validate_and_fix_action_list(messages, response_json, company_bot):
    """
    Validate and fix action list using end_context prompt.
    """
    context_data = {
        'response': response_json,
    }

    rendered_content = render_template_with_context(
        company_bot.tag_context, context_data
    )

    prompt = f"""
        {company_bot.context}
        {context_data}
        {rendered_content}
    """

    if company_bot and company_bot.provider == LLMProvider.OPENAI:
        system_prompt = [{"role": "system", "content": prompt}]

        tools = None
        tool_choice = None
        try:
            tool_context = json_repair.repair_json(company_bot.tool_context, return_objects=True)
            if tool_context:
                tools = tool_context.get("tool")
                tool_choice = tool_context.get("tool_choice", "auto")

            logger.info("Using state machine tool_context")
        except Exception as e:
            logger.error(f"Failed to parse state machine tool_context: {e}")

        logger.info("-----------------OPENAI PARALLEL---------------------------------", )
        logger.info(f"openai system_prompt: {system_prompt}")
        logger.info(f"openai messages: {messages}")
        validation_response = handle_openai_model(
            messages=messages, system_prompt=system_prompt, max_token=company_bot.max_token,
            temperature=company_bot.bot_temperature, company_bot=company_bot,
            top_p=company_bot.filter_score if company_bot.filter_score else None,
            tool_choice=tool_choice, tools=tools, stream=False, is_json_response=True
        )

    else:

        system_prompt = [{
            "text": prompt
        }]

        tool_context = company_bot.tool_context
        if tool_context:
            tool_context = json_repair.repair_json(tool_context, return_objects=True)

        validation_response = handle_bedrock_model(
            system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
            tools=tool_context, top_p=company_bot.filter_score,
        )

    logger.info(f"validation_response: {validation_response}")

    if not validation_response or not isinstance(validation_response, dict):
        logger.info("Invalid validation response from LLM")
        return response_json

    parsed_response = parse_validator_response(validation_response)

    if not parsed_response:
        logger.info("Failed to parse validation response")
        return response_json

    logger.info(f"Parsed validation response successfully")
    return parsed_response


def parse_validator_response(validation_response):
    """
    Parse validator LLM response into the expected format.
    """
    try:
        logger.info(f"validation_response: {validation_response}")

        if not validation_response or not isinstance(validation_response, dict):
            logger.info("Invalid validation response, returning None")
            return None

        if 'output' in validation_response:
            content = validation_response.get('output', {}).get('message', {}).get('content', [])
            if content and isinstance(content, list):
                for item in content:
                    if 'toolUse' in item:
                        tool_input = item['toolUse'].get('input', {})
                        if tool_input:
                            validation_response = tool_input
                            break

        extracted_data = validation_response.pop("parameters", validation_response.pop("input", None))
        if extracted_data:
            extracted_data = unwrap_tool_values(extracted_data)
            validation_response = extracted_data

        logger.info(f"extracted validation data: {extracted_data}")

        final_answer = validation_response.get('final_answer')
        if final_answer:
            if isinstance(final_answer, dict) and 'value' in final_answer:
                final_answer = final_answer['value']
            validation_response = final_answer

        if not isinstance(validation_response, dict):
            logger.info("Validation response is not a dict after extraction")
            return None

        return validation_response

    except Exception as e:
        logger.error(f"Error parsing validation response: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
