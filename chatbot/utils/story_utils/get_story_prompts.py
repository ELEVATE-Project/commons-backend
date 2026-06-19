from jinja2 import Template
import json_repair
from chatbot.models import Profile, LLMProvider
from chatbot.models.geo_models import ProfileAddress
from chatbot.utils.sql_utils import get_todays_date


def get_creation_promt(company_bot, profile):
    context = company_bot.context


    address = []

    if isinstance(profile, Profile):
        address = ProfileAddress.objects.filter(profile=profile)
    elif isinstance(profile, dict):
        address = profile.get('profile_address', [])

    state_machines = company_bot.companystatemachine_set.all().order_by('step')
    master_question = None

    if state_machines.exists():
        first_state_machine = state_machines.first()
        if first_state_machine.bot_question and first_state_machine.bot_question.strip():
            master_question = first_state_machine.bot_question.strip()

    context_data = {
        "profile": profile,
        "address": address if address else [{}],
    }

    if master_question:
        context_data["master_question"] = master_question

    template = Template(company_bot.tag_context)
    tag_context = template.render(context_data)

    end_context = company_bot.end_context
    project_data = ''
    today_date = get_todays_date(company_bot=company_bot)

    content_prompt = f"""
                {context}
                {tag_context}
                {today_date}
                {project_data}
            """ if context else None
    story_prompt = f"""
                {end_context}
                {tag_context}
                {today_date}
                {project_data}
            """ if end_context else None
    formatted_content_prompt = []
    formatted_story_prompt = []

    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        formatted_content_prompt = [
            {
                'text': content_prompt
            },
        ] if content_prompt else None
        formatted_story_prompt = [
            {
                'text': story_prompt
            },
        ] if story_prompt else None
    elif company_bot.provider == LLMProvider.OPENAI:
        formatted_content_prompt = [
            {
                'role': 'system',
                'content': content_prompt
            },
        ] if content_prompt else None
        formatted_story_prompt = [
            {
                'role': 'system',
                'content': story_prompt
            },
        ] if story_prompt else None

    return formatted_content_prompt, formatted_story_prompt, tag_context, project_data


def get_validation_prompt(
        response_json_story, validate_bot, response_json_content, tag_context, project_data, profile
):

    address = []

    if isinstance(profile, Profile):
        address = ProfileAddress.objects.filter(profile=profile)
    elif isinstance(profile, dict):
        address = profile.get('profile_address', [])

    state_machines = validate_bot.companystatemachine_set.all().order_by('step')
    master_question = None

    if state_machines.exists():
        first_state_machine = state_machines.first()
        if first_state_machine.bot_question and first_state_machine.bot_question.strip():
            master_question = first_state_machine.bot_question.strip()

    validate_context_data = {
        "story_json_output": response_json_story,
        "profile": profile,
        "address": address if address else [{}]
    }

    if master_question:
        validate_context_data["master_question"] = master_question

    validate_template = Template(validate_bot.tag_context)
    validate_tag_context = validate_template.render(validate_context_data)

    today_date = get_todays_date(company_bot=validate_bot)

    validate_story_prompt = f"""
               {validate_bot.end_context}
               {validate_tag_context}
               {tag_context}
                {today_date}
               {project_data}
           """ if validate_bot.end_context else None

    validate_context_data = {
        "story_json_output": response_json_content,
        "profile": profile,
        "address": address if address else [{}]
    }

    if master_question:
        validate_context_data["master_question"] = master_question

    validate_tag_context = validate_template.render(validate_context_data)

    validate_content_prompt = f"""
               {validate_bot.context}
               {validate_tag_context}
               {tag_context}
                {today_date}
               {project_data}
           """ if validate_bot.context else None

    if validate_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        validate_content_prompt = [
            {
                'text': validate_content_prompt
            },
        ] if validate_content_prompt else None
        validate_story_prompt = [
            {
                'text': validate_story_prompt
            },
        ] if validate_story_prompt else None
    elif validate_bot.provider == LLMProvider.OPENAI:
        validate_content_prompt = [
            {
                'role': 'system',
                'content': validate_content_prompt
            },
        ] if validate_content_prompt else None
        validate_story_prompt = [
            {
                'role': 'system',
                'content': validate_story_prompt
            },
        ] if validate_story_prompt else None

    return validate_content_prompt, validate_story_prompt


def get_chat_message(company_chats, company_bot):
    messages = []
    ai_user = Profile.objects.get(id=1)

    if company_chats and company_chats[0].receiver != ai_user:
        company_chats.pop(0)
    for chat in company_chats:
        user_message = chat.message
        if chat.receiver == ai_user:
            if chat.translated_message is not None and chat.translated_message != '':
                user_message = chat.translated_message
            if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                messages.append({
                    'role': 'user',
                    'content': [{'text': user_message}]
                })
            elif company_bot.provider == LLMProvider.OPENAI:
                messages.append({
                    'role': 'user',
                    'content': user_message
                })
        else:
            if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                messages.append({
                    'role': 'assistant',
                    'content': [{'text': user_message}]
                })
            elif company_bot.provider == LLMProvider.OPENAI:
                messages.append({
                    'role': 'assistant',
                    'content': user_message
                })


    return messages


def get_tool_values(company_bot):
    tool_context = company_bot.tool_context
    tool_context = json_repair.repair_json(tool_context, return_objects=True)
    tool_story = tool_context.get('story_tool')
    tool_content = tool_context.get('content_tool')

    return tool_content, tool_story


def get_challenges_prompt(challenges_faced, solutions_discussed, company_bot):
    context_data = {
        "challenges_faced": challenges_faced,
        "solutions_discussed": solutions_discussed,
    }
    template = Template(company_bot.context)
    updated_context = template.render(context_data)
    content_prompt=""
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        content_prompt = [
            {
                'text': updated_context
            },
        ]
    elif company_bot.provider == LLMProvider.OPENAI:
        content_prompt = [
            {
                'role': 'system',
                'content': updated_context
            },
        ]
    return content_prompt
