from chatbot.models import LLMProvider
from chatbot.utils.sql_utils import get_todays_date
from jinja2 import Template


def get_guided_prompt(company_bot, system_context, state_machine=None, intro_mssg=None, profile=None):
    prompt_to_use = []
    profile_addresses = None
    if profile and profile.first_name:
        profile_addresses = profile.profile_address.all().first()
    address_components = [
        profile_addresses.district if profile_addresses and profile_addresses.district else "",
        profile_addresses.block if profile_addresses and profile_addresses.block else "",
        profile_addresses.state if profile_addresses and profile_addresses.state else ""
    ]
    address_string = ", ".join(filter(None, address_components))

    today_date = get_todays_date(company_bot=company_bot)
    state_machine_context = ""
    state_machine_completion_criteria = ""
    if state_machine:
        state_machine_context = state_machine.context
        if intro_mssg:
            context_data = {
                "intro_message": intro_mssg,
                "user_location": address_string,
                "todays_date": today_date
            }
            template = Template(state_machine_context)
            state_machine_context = template.render(context_data)
        state_machine_completion_criteria = state_machine.completion_criteria

    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        prompt_to_use = [
            {
                'text': system_context
            },
            {
                'text': """
                {}

                {}

                Completion Criteria for function calling:
                {}
                """.format(today_date, state_machine_context, state_machine_completion_criteria)
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
                            {}

                            Completion Criteria:
                            {}""".format(
                    today_date,
                    system_context,
                    state_machine_context,
                    state_machine_completion_criteria
                )
            }
        ]

    return prompt_to_use
