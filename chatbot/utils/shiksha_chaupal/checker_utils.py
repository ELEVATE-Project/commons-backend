from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import LLMProvider
import logging
from jinja2 import Template


logger = logging.getLogger('django')


def prepare_missing_stage_questions(company_bot, state_machine, messages, extra_data="", profile=None):
    print("Preparing for llm call")
    system_context = company_bot.context
    if state_machine and state_machine.name == "CHECKER":
        prompt_to_use = get_guided_prompt(
            company_bot=company_bot, state_machine=state_machine, profile=profile
        )
    else:
        prompt_to_use= get_missing_question_prompt(
            company_bot=company_bot, system_context=system_context, state_machine=state_machine,
            checker_response=extra_data
        )
    response=''
    try:
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            try:
                response = handle_bedrock_model(
                    system_prompt=prompt_to_use, messages=messages, model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot
                )
            except Exception as e:
                logger.error(f"Got Error: %s", e)
                print(f"Got Error: {e}")
                response = None
        elif company_bot.provider == LLMProvider.OPENAI:
            response = handle_openai_model(
                system_prompt=prompt_to_use, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token,
                is_json_response=False
            )

        print("response_body bedrock: ", response)
        if response is None:
            response = ''
    except Exception as e:
        logger.error(f"Error: %s", e)
        print(f"Error: {e}")
        response = None

    return response


def get_guided_prompt(company_bot, state_machine, profile):
    prompt_to_use=[]
    profile_addresses=None
    if profile and profile.first_name:
        profile_addresses = profile.profile_address.all().first()
    address_components = [
        profile_addresses.district if profile_addresses and profile_addresses.district else "",
        profile_addresses.block if profile_addresses and profile_addresses.block else "",
        profile_addresses.state if profile_addresses and profile_addresses.state else ""
    ]
    address_string = ", ".join(filter(None, address_components))

    state_machine_context = state_machine.context
    context_data = {
        "user_location": address_string
    }
    template = Template(state_machine_context)
    state_machine_context = template.render(context_data)

    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        prompt_to_use = [
            {
                'text': """
                {}

                Completion Criteria for function calling:
                {}
                """.format(state_machine_context, state_machine.completion_criteria)
            },
            # {
            #     'text': company_bot.tool_context
            # }
        ]
    elif company_bot.provider == LLMProvider.OPENAI:
        prompt_to_use = [
            {
                'role': 'system',
                'content': """
                            {}

                            Completion Criteria:
                            {}""".format(
                    state_machine_context,
                    state_machine.completion_criteria
                )
            }
        ]

    return prompt_to_use


def get_missing_question_prompt(company_bot, system_context, state_machine, checker_response):
    print("Preparing for llm call")
    prompt_to_use=[]
    state_machine_context = state_machine.context
    state_machine_completion_criteria = state_machine.completion_criteria
    context_data = {
        "missing_questions": checker_response
    }
    template = Template(state_machine_context)
    template_completion_criteria = Template(state_machine_completion_criteria)
    state_machine_context = template.render(context_data)
    state_machine_completion_criteria = template_completion_criteria.render(context_data)
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        prompt_to_use = [
            {
                'text': system_context
            },
            {
                'text': """
                {}

                Completion Criteria for function calling:
                {}
                """.format(state_machine_context, state_machine_completion_criteria)
            },
            {
                'text': company_bot.tool_context
            }
        ]
    elif company_bot.provider == LLMProvider.OPENAI:
        prompt_to_use = [
            {
                'role': 'system',
                'content': """{}

                            {}

                            Completion Criteria:
                            {}""".format(
                    system_context,
                    state_machine_context, state_machine_completion_criteria
                )
            }
        ]

    return prompt_to_use
