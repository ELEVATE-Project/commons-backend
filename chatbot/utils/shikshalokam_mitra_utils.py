import os
import re
import requests
from datetime import timedelta, timezone
from pydantic_core._pydantic_core import ValidationError
from django.utils.timezone import now
from chatbot.models import Profile, CompanyChat, ChatSession
import json

from chatbot.utils.story_llama_utils import generate_random_hex
from shikshalokam.models import Project, Task
import ast


base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def create_project_utils(
    access_token,
    user_problem_statement,
    project_title,
    project_duration_weeks,
    user_action_steps,
    project_objective,
    original_project=None,
    chunks=None,
    session=None,
    status="completed",
):
    url = f"https://{base_url}/userProjects/add"

    headers = {
        "X-auth-token": access_token,
    }
    numeric_duration = extract_numeric(project_duration_weeks)
    print("numeric_duration: ", numeric_duration)
    start_date = now()
    start_date = start_date.astimezone(tz=timezone.utc)

    end_date = (start_date + timedelta(weeks=numeric_duration))
    start_date = start_date.isoformat()
    end_date = end_date.isoformat()
    conversation = []
    if session:
        company_chats = CompanyChat.objects.filter(session=session).order_by('created_at')

        conversation = get_stored_conversation(company_chats=company_chats)

    if original_project:
        chunks = original_project.project_source
        if not chunks:
            chunks = {}
        else:
            chunks = chunks.strip('{}')
            chunks = ast.literal_eval('{' + chunks + '}')
        print(type(chunks))
        chunks["projectId"]= original_project.project_id
        if original_project.template_id:
            chunks["projectTemplateId"]= original_project.template_id

    if not chunks:
        chunks = {"relevant_texts": []}

    print("final chunks: ", chunks)
    print("final chunks type: ", type(chunks))
    request_body = {
        "program": {
            "name": user_problem_statement,
            "startDate": start_date,
            "source": {
                "model": "llama3.1",
                "provider": "Bedrock"
            }
        },
        "projects": [
            {
                "conversation": conversation,
                "duration": f"{project_duration_weeks} week",
                "endDate": end_date,
                "source": chunks,
                "startDate": start_date,
                "status": status,
                "tasks": [
                    {
                        "isDeletable": True,
                        "name": step,
                        "source": {
                            "model": "llama3.1",
                            "provider": "Bedrock"
                        },
                    } for step in user_action_steps
                ],
                "title": project_title,
                "description": project_objective
            }
        ]
    }

    # print("req body: ", request_body)

    try:
        response = requests.post(url, headers=headers, json=request_body)
        print("response: ", response.json())
        response.raise_for_status()
        json_response = response.json()
        print("json_response: ", json_response)

        if not json_response or "result" not in json_response:
            raise ValidationError("Invalid response from the API")

        program_id = json_response["result"].get("programId")
        project_id = json_response["result"].get('projects')[0].get("_id")

        return {
            "original_response": json_response,
            "programId": program_id,
            "projectId": project_id,
            "chunks": chunks
        }

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while making the API call: {e}")
        return None
    except ValueError as e:
        print(f"Validation error: {e}")
        return None


def extract_numeric(value):
    if value:
        match = re.search(r'\d+', str(value))
        return int(match.group()) if match else None
    return None


def create_mitra_project_utils(
        chunks=None, actual_problem_statement=None, project_title=None, project_duration=None,
        project_objective=None, project_id=None, program_id=None, profile=None,
        language=None, session=None, user_action_steps = [], description=None
):
    try:

        chat_session = ChatSession.objects.filter(session=session).first()
        if chat_session and chat_session.project_id:
            project_id = chat_session.project_id

        if isinstance(user_action_steps, str):
            user_action_steps = json.loads(user_action_steps)

        if not isinstance(user_action_steps, list):
            user_action_steps = []

        if not project_id:
            project_id = generate_random_hex()
            print(f"Generated new project_id: {project_id}")

        print("project_id: ", project_id)
        print("="*50)
        default_values = {
            'author': profile,
            'expected_duration': project_duration,
            'expected_title': project_title,
            'expected_problem_statement': actual_problem_statement,
            'expected_objective': project_objective,
            'program_id': program_id,
            'project_source': chunks,
            'program_source':{
                "model": "llama3.3",
                "provider": "Bedrock"
            },
            'project_language': language,
            'description': description
        }
        for k,v  in list(default_values.items()):
            if v is None:
                del default_values[k]
        project, created = Project.objects.update_or_create(
            project_id=project_id,
            defaults=default_values
        )

        for action in user_action_steps:
            Task.objects.create(
                project=project,
                task_name=action,
                source={
                    "model": "llama3.3",
                    "provider": "Bedrock"
                }
            )

        if chat_session and not chat_session.project_id:
            chat_session.project_id = project_id
            chat_session.save(update_fields=["project_id"])

        return {
            "status": "success",
            "message": "Project and Task created successfully",
            "id": project.id,
            "project_id": project.project_id,
        }

    except Profile.DoesNotExist:
        return {"status": "error", "message": "Profile not found"}
    except Exception as e:
        return {"status": "error", "message": f"An error occurred: {str(e)}"}


def import_project_from_library_utils(access_token, program_name, project_template_id, program_id):
    url = f"https://{base_url}/userProjects/importFromLibrary/{project_template_id}"

    headers = {
        "X-auth-token": access_token,
    }

    request_body = {
        "programName": program_name,
        "programId": program_id
    }

    print("req body: ", request_body)

    try:
        response = requests.post(url, headers=headers, json=request_body)
        response.raise_for_status()
        json_response = response.json()
        print("json_response: ", json_response)

        if not json_response or "result" not in json_response:
            raise ValidationError("Invalid response from the API")

        return json_response

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while making the API call: {e}")
        return None
    except ValueError as e:
        print(f"Validation error: {e}")
        return None


def get_conversation(company_chats, ai_user):
    conversation = []
    for chat in company_chats:
        user_message = chat.message
        if chat.receiver == ai_user:
            if chat.translated_message is not None and chat.translated_message != '':
                user_message = chat.translated_message
            if conversation and len(conversation) > 0:
                conversation[-1]["userMessage"] = user_message

        else:
            conversation.append({
                "botResponse": user_message,
                "timestamp": chat.created_at.isoformat(),
                "userMessage": ""
            })
    print("\n\nconversation: ", conversation)

    return conversation


def get_stored_conversation(company_chats):
    ai_user = Profile.objects.values('id').get(id=1)
    conversation=[]
    for chat in company_chats:
        chat_receiver = None
        chat_message = None
        chat_translated_message = None
        chat_created_at = None
        
        # variable instialisation
        if isinstance(chat, CompanyChat):
            chat_receiver = getattr(chat.receiver, 'id', None)
            chat_message = getattr(chat, 'message', None)
            chat_translated_message = getattr(chat, 'translated_message', None)
            chat_created_at = getattr(chat, 'created_at', None)

        elif isinstance(chat, dict):
            chat_receiver = chat.get("receiver")
            chat_message = chat.get("message")
            chat_translated_message = chat.get("translated_message")
            chat_created_at = chat.get("created_at")

        if chat_receiver == ai_user.get("id"):
            user_message = chat_message
            if chat_translated_message is not None and chat_translated_message != '':
                user_message = chat_translated_message
            conversation.append({
                'user': user_message,
                'timestamp': chat_created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        else:
            conversation.append({
                'bot': chat_message,
                'timestamp': chat_created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

    return conversation

def get_stored_chathistory(company_chats):
    ai_user = Profile.objects.values("id").get(id=1)
    chat_history=[]
    for chat in company_chats:
        chat_receiver = None
        chat_message = None
        chat_translated_message = None
        chat_created_at = None
        chat_status = None
        
        # variable instialisation
        if isinstance(chat, CompanyChat):
            chat_receiver = getattr(chat.receiver, 'id', None)
            chat_message = getattr(chat, 'message', None)
            chat_translated_message = getattr(chat, 'translated_message', None)
            chat_created_at = getattr(chat, 'created_at', None)
            chat_status = getattr(chat, 'status', None)

        elif isinstance(chat, dict):
            chat_receiver = chat.get("receiver")
            chat_message = chat.get("message")
            chat_translated_message = chat.get("translated_message")
            chat_created_at = chat.get("created_at")
            chat_status = chat.get("status")

        if chat_receiver == ai_user.get("id"):
            user_message = chat_message
            if chat_translated_message is not None and chat_translated_message != '':
                user_message = chat_translated_message
            chat_history.append({
                'user': user_message,
                'timestamp': chat_created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'event': chat_status
            })
        else:
            chat_history.append({
                'bot': chat_message,
                'timestamp': chat_created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'event': chat_status
            })

    return chat_history
