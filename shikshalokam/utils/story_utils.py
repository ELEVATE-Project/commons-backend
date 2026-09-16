import json
import traceback
import os
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.contrib.sessions.backends.db import SessionStore
from chatbot.llm_models.llm_script import handle_llama_model, handle_openai_model
from chatbot.models import Company, CompanyBot, Story, StoryStatusChoices
from chatbot.utils.story_utils_test import get_formatted_story
from shikshalokam.models import Project

validate = URLValidator()

url = os.getenv('LLAMA_BASE_URL') + 'v1/chat/completions'


def create_story_object(profile_id=None, model_to_use=None):
    try:
        projects = get_project_queryset(profile_id=profile_id)
        company_bot = get_company_bot()

        for project in projects:
            create_story_from_project(project=project, company_bot=company_bot, model_to_use=model_to_use)

        return {"message": "STORY CREATION SUCCESS"}
    except Exception as e:
        traceback.print_exc()
        return {"error": "STORY CREATION ERROR"}


def create_story_from_project(project, company_bot, model_to_use):
    messages = [{
        'role': 'system',
        'content': get_story_prompt_context()
    }, {
        'role': 'user',
        'content': generate_story_context(project)
    }]
    print("MESSAGES: ", messages)
    if model_to_use in ['llama-normal', 'groq-llama', 'llama-finetune']:
        response_json = handle_llama_model(messages=messages, max_token=4096, temperature=0.7, top_p=0.9, seed=2322, n=1)
        print("\n\nResponse json: ", response_json)
        story = parse_story_response(response_json=response_json, project=project)
    else:
        response_json = handle_openai_model(company_bot=company_bot, messages=messages, max_token=4096, temperature=0.0)
        story = parse_story_response(response_json=response_json, project=project)
    return story


def parse_story_response(response_json, project):
    try:
        session = generate_session_id()

        story = Story(
            title=response_json['title'],
            content=response_json['content'],
            tweet=response_json['tweet'],
            author=project.author,
            session=session,
            objective=response_json['objective'],
            action_steps=response_json['action_steps'],
            impact=response_json['impact'],
            micro_improvement=response_json['micro_improvement'],
            stage=StoryStatusChoices.COMPLETED,
            other_params={'duration': response_json['duration']}
        )
        story.save()
        story.formatted_content = get_formatted_story(story)
        story.save(update_fields=['formatted_content'])

        project.story = story
        project.save()
        return story

    except Exception as e:
        traceback.print_exc()
        raise Exception("Error creating story from response")


def generate_session_id():
    try:
        session = SessionStore()
        session.create()
        return session.session_key
    except Exception as e:
        print('Exception is here')
        print(e)
        traceback.print_exc()


def is_url(value):
    try:
        validate(value)
        return True
    except ValidationError:
        return False


def get_project_queryset(profile_id=None):
    if profile_id:
        return Project.objects.filter(
            story=None, author=profile_id
        ).select_related('author').prefetch_related('evidence', 'task')
    return Project.objects.filter(story=None).select_related('author').prefetch_related('evidence', 'task')


def get_company_bot():
    try:
        company = Company.objects.get(slug='shikshalokam')
        company_bot = CompanyBot.objects.filter(company=company).first()
        return company_bot
    except Company.DoesNotExist:
        raise Exception("Company not found")


def get_evidence_data(evidence):
    evidence_link = evidence.evidence_link
    if evidence_link and not is_url(evidence_link):
        return {'remark': evidence.remark, 'evidence_text': evidence_link}
    if is_url(evidence_link):
        return {'remark': evidence.remark}
    return None


def generate_story_context(project):
    project_details = {
        'evidences': [data for evidence in project.evidence.all() if (data := get_evidence_data(evidence))],
    }
    task_details = [
        {
            'task_name': task.task_name if not is_url(task.task_name) else None,
            'observation_name': task.observation_name,
            'number_of_submission_observation': task.number_of_submission_observation,
        } for task in project.task.all()
    ]

    return f"""
        Here are the details of a user project which need to be incorporated into the generated story. 
        Use these details to craft a narrative that reflects the essence of the project:

        - **Project Title**: {project.title}
        - **Project Objective**: {project.objective}
        - **Project Start Date**: {project.project_start_date}
        - **Project End Date**: {project.project_end_date}
        - **Project Duration**: {project.duration}
        - **Project Evidences**: {json.dumps(project_details['evidences'], indent=4)}
        - **Project Learning Resource Name**: {project.resource_name}
        - **Project Learning Resource Link**: {project.resource_link}
        - **Task Details**: {json.dumps(task_details, indent=4)}
    """



def get_story_prompt_context():
    return """
        Use this project information from the user to create a detailed story that includes a title, content, tweet,
        objective, action steps, impact, and the importance of the micro-improvement made through the project.
        THINGS TO INCORPORATE:
        1. USE PRESENT TENSE
        2. DO NOT USE CLICHE BEGINNINGS
        3. DO NOT ADD FLUFF DO NOT USE FLOWERY LANGUAGE.
        OUTPUT VALID JSON FORMAT:
        {
            "title": "Title of the story",
            "duration": "Total time span of the project, from start to end",
            "content": "Content of the story in more than 600 tokens",
            "tweet": "Tweet for the story in less than 200 characters with minimum 5 hashtags",
            "objective": "Objective of the micro improvement",
            "action_steps": "5 Action steps taken by the user to implement the micro improvement",
            "impact": "Impact created from this micro improvement",
            "micro_improvement": "Why is this micro-improvement important"
        }
    """

