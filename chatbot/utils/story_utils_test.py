import json
import traceback
import random
import string
from chatbot.models import (Profile, CompanyChat, CompanyBot, StoryLanguageChoices,
                            StoryStatusChoices, ChatSession, ChatStatus, Voice, VoiceType, BotVernacular,
                            SessionFlowName)
from chatbot.models.geo_models import ProfileAddress
from chatbot.models.story_models import Story
from chatbot.utils.shikshalokam_mitra_utils import get_stored_conversation, get_stored_chathistory
from chatbot.utils.shikshalokam_story_utils import save_shikshalokam_story
from chatbot.utils.story_llama_utils import create_project, translate_field
from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.utils.story_utils.story_llm import generate_story_llm
from shikshalokam.models import Project, Task
from shikshalokam.serializer import TaskSerializer
from shikshalokam.utils.project_utils import get_project_formatted_data
from jinja2 import Template
import json_repair
import asyncio
import functools


def create_story_object(profile_id, session, access_token, flow, language='en'):
    error_message = ""
    voice_provider=None
    try:
        profile = Profile.objects.get(id=profile_id)
        company_chats = CompanyChat.objects.filter(session=session).order_by('created_at')
        ai_user = Profile.objects.get(id=1)
        company_bot = CompanyBot.objects.get(route='/story')
        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        if bot_vernacular:
            error_message = bot_vernacular.error_message
        else:
            error_message = "Please try again!"

        voice_provider = Voice.objects.filter(company_bot=company_bot, type=VoiceType.TextToText).first()
        reflection_bot = CompanyBot.objects.filter(route='/reflection').first()
        validate_bot = CompanyBot.objects.get(route='/story_validation')
        context = company_bot.context
        address = ProfileAddress.objects.filter(profile=profile)
        context_data = {
            "profile": profile,
            "address": address if address else [{}]
        }
        template = Template(company_bot.tag_context)

        tag_context = template.render(context_data)

        end_context = company_bot.end_context

        chat_session = ChatSession.objects.get(session=session)
        project_id = chat_session.project_id

        if flow == SessionFlowName.Reflection and project_id and reflection_bot:
            reflection_end_context = reflection_bot.end_context
            user_project = Project.objects.filter(project_id=project_id).first()
            project_data = get_project_formatted_data(user_project=user_project)
            project_data = reflection_end_context.format(**project_data)
            print("project_data: ", project_data)
            if language != 'en':
                project_data = translate_field(
                    voice_provider=voice_provider, message_body=project_data,
                    source_language=language, target_language='en'
                )
                print("translated project_data: ", project_data)
        else:
            project_data = ''

        content_prompt = f"""
            {context}
            {tag_context}
            {project_data}
        """
        story_prompt = f"""
            {end_context}
            {tag_context}
            {project_data}
        """
        print('-------------------------------')
        print(story_prompt)

        messages=[]
        formatted_content_prompt = [
            {
                'text': content_prompt
            },
        ]
        formatted_story_prompt = [
            {
                'text': story_prompt
            },
        ]
        if company_chats and company_chats[0].receiver != ai_user:
            company_chats.pop(0)
        for chat in company_chats:
            user_message = chat.message
            if chat.receiver == ai_user:
                if chat.translated_message is not None and chat.translated_message != '':
                    user_message = chat.translated_message
                messages.append({
                    'role': 'user',
                    'content': [{'text': user_message}]
                })
            else:
                messages.append({
                    'role': 'assistant',
                    'content': [{'text': user_message}]
                })

        # print("Message: ", messages)
        tool_context = company_bot.tool_context
        tool_context = json_repair.repair_json(tool_context, return_objects=True)
        tool_story = tool_context.get('story_tool')
        tool_content = tool_context.get('content_tool')
        print("\n----------")
        response_json_content, response_json_story = asyncio.run(
            generate_story_llm(
                formatted_content_prompt=formatted_content_prompt, formatted_story_prompt=formatted_story_prompt,
                messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=company_bot
            )
        )
        print("\n\nresponse_json_content: ", response_json_content)
        print("\n\nresponse_json_story: ", response_json_story)
        validate_context_data = {
            "story_json_output": response_json_story,
        }
        validate_template = Template(validate_bot.tag_context)
        validate_tag_context = validate_template.render(validate_context_data)

        validate_story_prompt = f"""
            {validate_bot.end_context}
            {validate_tag_context}
            {tag_context}
            {project_data}
        """

        validate_context_data = {
            "story_json_output": response_json_content,
        }
        validate_tag_context = validate_template.render(validate_context_data)

        validate_content_prompt = f"""
            {validate_bot.context}
            {validate_tag_context}
            {tag_context}
            {project_data}
        """

        validate_content_prompt = [
            {
                'text': validate_content_prompt
            },
        ]
        validate_story_prompt = [
            {
                'text': validate_story_prompt
            },
        ]

        tool_context = validate_bot.tool_context
        tool_context = json_repair.repair_json(tool_context, return_objects=True)
        tool_story = tool_context.get('story_tool')
        tool_content = tool_context.get('content_tool')
        print("------------------------------------------")
        print("\n\nvalidate_content_prompt: ", validate_content_prompt)
        print("\n\nvalidate_story_prompt: ", validate_story_prompt)
        print("------------------------------------------")
        response_json_story, combined_reason = asyncio.run(
            validate_story_llm(
                formatted_content_prompt=validate_content_prompt, formatted_story_prompt=validate_story_prompt,
                messages=messages, tool_content=tool_content, tool_story=tool_story, company_bot=validate_bot
            )
        )
        print("\n\nvalidated_result: ", response_json_story)
        print("\n\ntype validated_result: ", type(response_json_story))
        print("\n\ncombined_reason: ", combined_reason)
        print("\n----------")

        title = response_json_story.get('title', '')
        print('title: ', title)
        tweet = response_json_story.get('tweet', '')
        print('tweet: ', tweet)
        objective = response_json_story.get('objective', '')
        print('objective: ', objective)
        action_steps = response_json_story.get('action_steps', '')
        print('action_steps: ', action_steps)
        impact = response_json_story.get('impact', '')
        print('impact: ', impact)
        micro_improvement = response_json_story.get('micro_improvement', '')
        print('micro_improvement: ', micro_improvement)
        problem_statement = response_json_story.get('problem_statement', '')
        print('problem_statement: ', problem_statement)

        duration = response_json_story.get('duration', '')
        other_params = {
            'duration': duration
        }

        content = response_json_story.get('content', '')
        print('content: ', content)
        blurb = response_json_story.get('blurb', '')
        print('blurb: ', blurb)
        content = clean_escaped_text(text=content)
        print('clean content: ', content)

        print("language used: ", language)
        if language != 'en':
            title = translate_field(
                voice_provider=voice_provider, message_body=title, target_language=language
            )
            tweet = translate_field(
                voice_provider=voice_provider, message_body=tweet, target_language=language
            )
            objective = translate_field(
                voice_provider=voice_provider, message_body=objective, target_language=language
            )
            action_steps = translate_field(
                voice_provider=voice_provider, message_body=action_steps, target_language=language
            )
            impact = translate_field(
                voice_provider=voice_provider, message_body=impact, target_language=language
            )
            micro_improvement = translate_field(
                voice_provider=voice_provider, message_body=micro_improvement, target_language=language
            )
            problem_statement = translate_field(
                voice_provider=voice_provider, message_body=problem_statement, target_language=language
            )
            content = translate_field(
                voice_provider=voice_provider, message_body=content, target_language=language
            )
            blurb = translate_field(
                voice_provider=voice_provider, message_body=blurb, target_language=language
            )
        if flow == SessionFlowName.Reflection:
            print("project_id: ", project_id)
            project = Project.objects.get(project_id=project_id)
            if project:
                print("project: ", project)
                tasks = Task.objects.filter(project=project)
                serialized_tasks = TaskSerializer(tasks, many=True).data
                print("tasks serialized_tasks: ", serialized_tasks)
                # action_steps = [task.get('task_name') for task in serialized_tasks]
                action_steps = [f"{idx + 1}. {task.get('task_name')}" for idx, task in enumerate(serialized_tasks)]
                print("tasks action_steps: ", action_steps)

        if profile:
            address = ProfileAddress.objects.filter(profile=profile).first()
            if address:
                location_parts = filter(None, [address.block, address.district, address.state])
                location = ", ".join(location_parts)
            else:
                location = ""
        else:
            location = ""

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = title
            story.content = content
            story.tweet = tweet
            story.author = profile
            story.objective = objective
            story.action_steps = action_steps
            story.impact = impact
            story.micro_improvement = micro_improvement
            story.language = StoryLanguageChoices.ENGLISH
            story.stage = StoryStatusChoices.COMPLETED
            story.other_params = other_params
            story.location = location
            story.blurb = blurb
            story.validation_logs = combined_reason
        else:
            story = Story(
                title=title,
                content=content,
                tweet=tweet,
                author=profile,
                session=session,
                objective=objective,
                action_steps=action_steps,
                impact=impact,
                micro_improvement=micro_improvement,
                language=StoryLanguageChoices.ENGLISH,
                stage=StoryStatusChoices.COMPLETED,
                other_params=other_params,
                location=location,
                blurb=blurb,
                validation_logs=combined_reason
            )

        story.save()
        formatted_content = get_formatted_story(story)
        story.formatted_content = formatted_content
        story.save(update_fields=['formatted_content'])

        create_project(
            response_json=response_json_story,title=title, objective=objective, story=story,
            profile=profile, problem_statement=problem_statement, project_id=project_id, language=language,
            voice_provider=voice_provider
        )

        chat_session.session_status = ChatStatus.COMPLETED
        chat_session.save(update_fields=['session_status'])
        chat_session.save_title(language=language)
        conversation = get_stored_conversation(company_chats=company_chats)
        chat_history = get_stored_chathistory(company_chats=company_chats)

        save_shikshalokam_story(
            story=story, access_token=access_token,
            problem_statement=problem_statement, project_id=project_id, session=session,
            profile=profile, conversation=conversation, flow=flow, chat_history=chat_history
        )

        return story.id, story.content, ""

    except Exception as e:
        print("Error msg in except: ", error_message)
        print("voice_provider in except: ", voice_provider)
        if voice_provider and error_message and language != 'en':
            error_message=translate_field(
                voice_provider=voice_provider, message_body=error_message, target_language=language
            )
        traceback.print_exc()
        return "", "", error_message


def format_response_json(response):
    response_json = response.replace('\n', '').replace('\t', '').replace(
        '\r', '').replace('\\n', '').replace('\\t', '').replace('\\r', '')
    if '{' in response_json:
        response_json = response_json[response_json.index('{'):]
    last_char = response_json[-1]
    if last_char != '}':
        response_json += '}'
    print("\nBEFORE LOADS: ", response_json)
    if isinstance(response_json, str):
        response_json = json_repair.repair_json(response_json, return_objects=True)
        print("AFTER LOADS: ", response_json)
    print("TYPE response_json: ", type(response_json))

    return response_json


def get_formatted_story(story):
    story_paragraphs = story.content.split("\n")
    res = []
    for paragraph in story_paragraphs:
        res.append(
            {
                'id': generate_random_string(10),
                'type': 'paragraph',
                'data':
                    {
                        'text': paragraph,
                    }
            }
        )
    return json.dumps(res)


def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    rs = ''.join(random.choice(characters) for _ in range(length))
    return rs


async def validate_story_llm(formatted_content_prompt, formatted_story_prompt, messages, tool_content, tool_story,
                             company_bot):
    async def func1():
        print("Running func1")
        return await asyncio.to_thread(
            functools.partial(
                handle_bedrock_model,
                system_prompt=formatted_content_prompt,
                messages=messages,
                tools=tool_content,
                temperature=company_bot.bot_temperature,
                max_token=company_bot.max_token,
                top_p=company_bot.filter_score,
                model_name=company_bot.llm_model,
                company_bot=company_bot
            )
        )

    async def func2():
        print("Running func2")
        return await asyncio.to_thread(
            functools.partial(
                handle_bedrock_model,
                system_prompt=formatted_story_prompt,
                messages=messages,
                tools=tool_story,
                temperature=company_bot.bot_temperature,
                max_token=company_bot.max_token,
                top_p=company_bot.filter_score,
                model_name=company_bot.llm_model,
                company_bot=company_bot
            )
        )

    response_json_content, response_json_story = await asyncio.gather(func1(), func2())
    print("response_json_content: ", response_json_content)
    print("response_json_story: ", response_json_story)
    for response in [response_json_content, response_json_story]:
        if response and isinstance(response, dict):
            extracted_data = response.pop("parameters", response.pop("input", None))
            if extracted_data and isinstance(extracted_data, dict):
                response.clear()
                response.update(extracted_data)

    reason_content = response_json_content.get('reason')
    response_json_content = response_json_content.get('final_answer')
    if response_json_content and isinstance(response_json_content, str):
        response_json_content = json_repair.repair_json(response_json_content, return_objects=True)

    reason_story = response_json_story.get('reason')
    response_json_story = response_json_story.get('final_answer')
    if response_json_story and isinstance(response_json_story, str):
        response_json_story = json_repair.repair_json(response_json_story, return_objects=True)

    print("response_json_content: ", response_json_content)
    print("response_json_story: ", response_json_story)

    if (isinstance(response_json_story, dict) and response_json_story.get("type") == "string" and
            "value" in response_json_story):
        value = response_json_story.get("value")
        if isinstance(value, str) and value.strip():
            response_json_story = json_repair.repair_json(value, return_objects=True)

    if (isinstance(response_json_content, dict) and response_json_content.get("type") == "string" and
            "value" in response_json_content):
        value = response_json_content.get("value")
        if isinstance(value, str) and value.strip():
            response_json_content = json_repair.repair_json(value, return_objects=True)

    combined_result = {**response_json_content, **response_json_story}
    combined_reason = {
        "reason_content": reason_content,
        "reason_story": reason_story
    }

    return combined_result, combined_reason


def clean_escaped_text(text):
    text = text.replace("\\'", "")# \'  →  '
    text = text.replace('\\"', '')# \"  →  "
    text = text.replace("\\\\", "") # \\  →  \
    print("Text: ", text)
    return text
