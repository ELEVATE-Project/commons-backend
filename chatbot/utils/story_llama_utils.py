import json
import secrets
import traceback
from datetime import datetime
from chatbot.utils.audio_provider_utils import text_translate_provider
from shikshalokam.models import Project, ProjectStatus, ProjectVernacular, Task
import logging

logger = logging.getLogger('django')


def create_project(response_json, title, objective, story, profile, problem_statement, project_id, language,
                   voice_provider, action_steps=None):
    try:
        resource_name = response_json.get('resource_name', '')
        resource_link = response_json.get('resource_link', '')
        duration = story.other_params.get('duration', '') if story.other_params else ''
        keywords = response_json.get('keywords', '')
        project_start_date = parse_datetime(response_json.get('project_start_date', ''))
        project_end_date = parse_datetime(response_json.get('project_end_date', ''))

        if not project_id:
            existing_project = Project.objects.filter(story=story).first()
            if existing_project:
                project_id = existing_project.project_id
                print(f"Found existing project for story: {project_id}")
            else:
                project_id = generate_random_hex()
                print(f"Generated new project_id: {project_id}")

        llm_source = "UNKNOWN"
        if voice_provider and voice_provider.company_bot:
            company_bot = voice_provider.company_bot

            provider = company_bot.provider or "unknown_provider"
            model = company_bot.llm_model or "unknown_model"

            llm_source = f"{provider}:{model}"

        project, created = Project.objects.update_or_create(
            project_id=project_id,
            defaults={
                "story": story,
                "author": profile,
                "actual_title": title,
                "actual_objective": objective,
                "actual_duration": duration,
                "project_status": ProjectStatus.SUBMITTED,
                "actual_problem_statement": problem_statement,
                "keywords": keywords,
                'project_source': llm_source,
                'program_source': llm_source,
                "resource_name": resource_name,
                "resource_link": resource_link,
                "project_start_date": project_start_date,
                "project_end_date": project_end_date,
                "project_language": "en"
            }
        )

        if created:
            print("A new project was created.")
        else:
            print("The existing project was updated.")

        project.save()

        if action_steps:
            if isinstance(action_steps, str):
                action_steps = [action_steps]
            if created:
                for idx, step in enumerate(action_steps):
                    cleaned_step = step.strip()
                    if not cleaned_step:
                        continue
                    task = Task.objects.create(
                        project=project,
                        task_id=generate_random_hex(8),
                        parent_task_id=None,
                        task_name=cleaned_step,
                        mandatory_task=None,
                        task_status="COMPLETED",
                        description=cleaned_step,
                        source=llm_source,
                        other_params={
                            "order": idx + 1,
                            "generated_from": "action_steps"
                        },
                        created_by=profile.user if hasattr(profile, "user") else None
                    )

                    if language != 'en':
                        task_data = {'task_name': cleaned_step}
                        create_task_vernacular(
                            task=task, language=language, voice_provider=voice_provider, task_data=task_data
                        )

                print(f"{len(action_steps)} tasks created for project {project.project_id}")

        if language != 'en':
            create_project_vernacular(
                project=project,
                language=language,
                voice_provider=voice_provider,
                project_data={
                    'actual_title': title,
                    'actual_objective': objective,
                    'actual_problem_statement': problem_statement,
                    'actual_duration': duration,
                    'keywords': keywords,
                    'resource_name': resource_name,
                    'resource_link': resource_link
                },
            )

        return story.id, story.content

    except Exception as e:
        traceback.print_exc()
        return "", ""


def create_project_vernacular(project, language, voice_provider, project_data):
    """Create ProjectVernacular entry with translated project data"""
    try:
        print("create_project_vernacular")
        translated_data = {}

        translatable_fields = [
            'actual_title', 'actual_objective', 'actual_problem_statement',
            'keywords', 'resource_name'
        ]

        for field in translatable_fields:
            field_value = project_data.get(field, '')
            if field_value and field_value != '':
                translated_value = translate_field(
                    voice_provider=voice_provider,
                    message_body=field_value,
                    target_language=language
                )
                translated_data[field] = translated_value
            else:
                translated_data[field] = field_value

        story = project.story
        if story:
            try:
                story_translation = story.translations.get(language=language)
                translated_data['actual_duration'] = story_translation.other_params.get(
                    'duration', ''
                ) if story_translation.other_params else ''
            except:
                translated_data['actual_duration'] = story.other_params.get(
                    'duration', ''
                ) if story.other_params else ''
        else:
            translated_data['actual_duration'] = ''

        translated_data['resource_link'] = project_data.get('resource_link', '')

        project_vernacular, created = ProjectVernacular.objects.update_or_create(
            project=project,
            language=language,
            defaults={
                'details': json.dumps({"project": translated_data}, ensure_ascii=False)
            }
        )

        if created:
            print(f"Created ProjectVernacular for language: {language}")
        else:
            print(f"Updated ProjectVernacular for language: {language}")

        return project_vernacular

    except Exception as e:
        print(f"Error creating ProjectVernacular: {e}")
        traceback.print_exc()
        return None


def create_task_vernacular(task, language, voice_provider, task_data):
    if language != 'en' and voice_provider:
        translated_task_name = translate_field(
            voice_provider=voice_provider,
            message_body=task_data.get('task_name'),
            target_language=language
        )

        ProjectVernacular.objects.update_or_create(
            task=task,
            language=language,
            details=json.dumps({
                "task_name": translated_task_name,
                "description": translated_task_name
            }, ensure_ascii=False),
        )


def generate_random_hex(length=16):
    return secrets.token_hex(length)


def parse_datetime(date_str):
    try:
        if date_str:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    return None


def translate_field(voice_provider, message_body, target_language, source_language="en"):
    print(f"Trying to translate: {message_body}")
    logger.info(f"Trying to translate: {message_body}")
    if not message_body or message_body == '' or source_language == target_language:
        logger.info(
            f"Skipping translation; returning original message. body='{message_body}', source='{source_language}',"
            f" target='{target_language}'")

        return message_body

    response = text_translate_provider(
        voice_provider=voice_provider, message_body=message_body, target_language=target_language,
        source_language=source_language
    )
    if response.get('status') == 200:
        logger.info(f"Got 200 response from translation service: {response.get('content')}")
        return response.get('content')
    else:
        logger.info(f"Translation service returned non-200; using original text: {message_body}")
        return message_body
