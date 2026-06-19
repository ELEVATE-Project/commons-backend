from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.models import CompanyBot
from chatbot.utils.shikshalokam_mitra_utils import create_mitra_project_utils
from shikshalokam.utils.action_list.action_parser import unwrap_tool_values
from shikshalokam.utils.action_list.action_validator import validate_and_fix_action_list
import json
import logging

logger = logging.getLogger('django')

def get_mitra_paraphrase_utils(messages, company_bot, session_id):
    paraphrase_prompt = company_bot.context
    paraphrase_prompt = [{'text': paraphrase_prompt}]

    paraphrase_response = handle_bedrock_model(
        system_prompt=paraphrase_prompt, messages=messages, model_name = company_bot.llm_model,
        temperature = company_bot.bot_temperature, max_token = company_bot.max_token, company_bot=company_bot, tools=json.loads(company_bot.tool_context)
    )


    logger.info("Paraphrased response: %s", json.dumps(paraphrase_response))

    validated_response = None
    try:
        validate_bot = CompanyBot.objects.filter(route='/paraphrase_bot').first()
        if validate_bot:
            validated_response = validate_and_fix_action_list(
                messages=messages, response_json=paraphrase_response, company_bot=validate_bot
            )

            logger.info("Validation response: %s", json.dumps(validated_response))
            logger.info("Validation applied using validate_bot for paraphrase")
        else:
            logger.info("No validate_bot found with route='/paraphrase_bot', skipping validation")

    except CompanyBot.DoesNotExist:
        logger.error("validate_bot not found, proceeding without validation")
    except Exception as validation_error:
        logger.error(f"Validation failed: {validation_error}, proceeding with original response")

    final_response = paraphrase_response
    create_mitra_project_utils(session=session_id, description=json.dumps(final_response))

    if validated_response:
        final_response = validated_response

    if 'output' in final_response:
        content = (
            final_response
            .get('output', {})
            .get('message', {})
            .get('content', [])
        )

        if isinstance(content, list):
            for item in content:
                if 'toolUse' in item:
                    tool_input = item['toolUse'].get('input')
                    if tool_input:
                        final_response = tool_input
                        break

    extracted_data = (
            final_response.pop("parameters", None)
            or final_response.pop("input", None)
    )

    if extracted_data:
        extracted_data = unwrap_tool_values(extracted_data)
        final_response = extracted_data

    logger.info(
        "Extracted paraphrase data: %s",
        json.dumps(final_response, default=str)
    )

    if isinstance(final_response, str):
        try:
            final_response = json.loads(final_response)
        except Exception:
            import json_repair
            final_response = json_repair.repair_json(
                final_response, return_objects=True
            )

    return final_response


def generate_title_utils(input_data, company_bot):
    prompt = company_bot.context
    messages = [{
        'role': 'user',
        'content': [{'text': f"{input_data}"}]
    }]

    prompt = [{'text': prompt}]

    response = handle_bedrock_model(
        system_prompt=prompt, messages=messages, model_name = company_bot.llm_model,
        temperature = company_bot.bot_temperature, max_token = company_bot.max_token,
        company_bot=company_bot
    )
    response = response.get('title')
    return response
