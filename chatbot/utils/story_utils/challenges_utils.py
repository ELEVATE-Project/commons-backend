from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import CompanyBot, LLMProvider
from chatbot.utils.story_utils.get_story_prompts import get_challenges_prompt
import json_repair
import logging


logger = logging.getLogger('django')



def handle_challenges_solutions(challenges_faced, solutions_discussed, profile, messages):
    if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/chaupal-story-challenge')
    else:
        company_bot = CompanyBot.objects.get(route='/chaupal-story-challenge')

    system_context = get_challenges_prompt(
        challenges_faced=challenges_faced, solutions_discussed=solutions_discussed,
        company_bot=company_bot
    )
    response_json = None
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        tool = company_bot.tool_context
        if tool and isinstance(tool, str):
            tool = json_repair.repair_json(tool, return_objects=True)
        response_json = handle_bedrock_model(
            system_prompt=system_context, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
            tools=tool, company_bot=company_bot
        )
    elif company_bot.provider == LLMProvider.OPENAI:
        response_json = handle_openai_model(
            system_prompt=system_context, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
            is_json_response=True
        )
    if response_json and isinstance(response_json, str):
        response_json = json_repair.repair_json(response_json, return_objects=True)

    if response_json and isinstance(response_json, dict):
        extracted_data = response_json.pop("parameters", response_json.pop("input", None))
        if extracted_data and isinstance(extracted_data, dict):
            response_json.clear()
            response_json.update(extracted_data)
        if (isinstance(response_json, dict) and response_json.get("type") and
                "value" in response_json):
            value = response_json.get("value")
            if isinstance(value, str) and value.strip():
                value = json_repair.repair_json(value, return_objects=True)
            response_json = value
        logger.info(f"response_json: %s", response_json)

        reorder_steps = response_json.get('reorder_steps', [])
        if reorder_steps and isinstance(reorder_steps, str):
            reorder_steps = json_repair.repair_json(reorder_steps, return_objects=True)
        if reorder_steps and not isinstance(reorder_steps, list):
            logger.info('reordersteps is not a list, getting values')
            if reorder_steps.get('value'):
                reorder_steps = reorder_steps.get('value')
                      
        logger.info(f"reorder_steps: %s", reorder_steps)

        seen = set()
        new_solutions_discussed = []

        for step in reorder_steps:
            matched = step.get('solution_matched', [])
            if isinstance(matched, list) and matched:
                for solution in matched:
                    if solution and solution not in seen:
                        seen.add(solution)
                        new_solutions_discussed.append(solution)
            elif isinstance(matched, str) and matched:
                if matched not in seen:
                    seen.add(matched)
                    new_solutions_discussed.append(matched)

        if not new_solutions_discussed or len(new_solutions_discussed) == 0:
            new_solutions_discussed = solutions_discussed
    else:
        new_solutions_discussed = solutions_discussed

    return challenges_faced, new_solutions_discussed
