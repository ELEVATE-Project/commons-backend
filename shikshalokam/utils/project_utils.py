import json
import traceback
import os
import requests

from chatbot.models import SessionFlowName, CompanyChat, Profile, StoryMedia, MediaTypeChoices
from chatbot.utils.shikshalokam_mitra_utils import get_stored_conversation, get_stored_chathistory
from shikshalokam.models import Task, Project


base_url = os.getenv("SHIKSHALOKAM_BASE_URL")


def update_project_status_utils(project_id, access_token, status):
    try:
        url = f"https://{base_url}/userProjects/update/{project_id}"
        print("using url: ", url)
        if access_token.startswith('"') and access_token.endswith('"'):
            access_token = access_token[1:-1]
        headers = {
            "X-auth-token": access_token,
        }

        request_body = {
            "reflectionStatus": status
        }
        print("request_body: ", request_body)
        print("request_body: ", request_body)
        print("type: ", type(request_body))
        print("type: ", type(request_body.get("story")))
        response = requests.post(url, headers=headers, json=request_body)
        print("Response: ", response)
        print("response: ", response.json())

        return response.json()

    except Exception as e:
        traceback.print_exc()
        print(f"Failed to update project status: {str(e)}")


def get_project_formatted_data(user_project):
    tasks = Task.objects.filter(project=user_project)
    task_names = [task.task_name for task in tasks]
    task_names_str = ', '.join(task_names)

    project_data = {
        'problem_statement': user_project.expected_problem_statement,
        'objective': user_project.expected_objective,
        'action_steps': task_names_str,
        'duration': user_project.expected_duration.strip() + " week"
        if "week" not in user_project.expected_duration.lower() else user_project.expected_duration
    }
    print("Using project data: ", project_data)

    return project_data


def check_and_save_project(project_id, access_token, profile):
    if not Project.objects.filter(project_id=project_id).exists():
        print(f"Project {project_id} not found. Fetching from API...")
        fetch_and_save_project(project_id=project_id, access_token=access_token, profile=profile)


def fetch_and_save_project(project_id, access_token, profile):

    try:
        url = f"https://{base_url}/userProjects/details/{project_id}"
        print("using url: ", url)
        headers = {
            "X-auth-token": access_token,
        }
        payload = {}

        response = requests.request("POST", url, headers=headers, data=payload)
        response_json = response.json()
        print("response: ", response_json)


        result = response_json.get("result")
        project_status = result.get('status', '').upper() if result.get('status') else None



        project = Project.objects.create(
            project_id=result.get("_id"),
            recommended_for= json.dumps(result.get('recommendedFor')),
            expected_title= result.get('title'),
            categories= json.dumps(result.get('categories')),
            expected_duration=result.get('duration'),
            project_start_date=result.get('startDate'),
            project_end_date=result.get('endDate'),
            program_id= result.get('programId'),
            program_name = result.get('programName'),
            expected_problem_statement= result.get('programName'),
            project_status=project_status,
            project_source = result.get('source'),
            expected_objective= result.get('description'),
            author=profile,
            # "generated_by": ProjectCreatedBy.EXPERT_VETTED
        )
        tasks = result.get('tasks', [])
        for task_data in tasks:
            Task.objects.get_or_create(
                project=project,
                task_id=task_data.get('_id'),
                defaults={"task_name": task_data.get('name', '')}
            )
        print(f"Project {project_id} saved successfully.")


    except Exception as e:
        traceback.print_exc()
        print(f"Failed to save project: {str(e)}")
