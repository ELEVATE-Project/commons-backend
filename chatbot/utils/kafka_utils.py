import json

from chatbot.models import Profile
from shikshalokam.models import Project, Category, ProjectTemplate, Task
from django.db import transaction


def update_project_in_db(project_data):
    if project_data:
        project_id = project_data.get("_id")
        if project_id:
            try:
                with transaction.atomic():
                    current_project = Project.objects.get(project_id=project_id)

                    current_project.project_status = project_data.get('status', current_project.project_status)
                    current_project.categories = json.dumps(project_data.get('categories', current_project.categories))
                    current_project.template_id = project_data.get('projectTemplateId', current_project.template_id)
                    current_project.recommended_for = json.dumps(project_data.get('recommendedFor',
                                                                       current_project.recommended_for))
                    current_project.actual_title = project_data.get('title', current_project.actual_title)
                    current_project.description = project_data.get('description', current_project.description)
                    current_project.program_id = project_data.get('programId', current_project.program_id)
                    current_project.program_name = project_data.get(
                        'programInformation', {}
                    ).get("name", current_project.program_name)

                    current_project.save()

                    tasks = project_data.get("tasks")
                    if tasks:
                        for task_data in tasks:
                            task_id = task_data.get("_id")
                            if task_id:
                                Task.objects.update_or_create(
                                    task_id=task_id,
                                    project=current_project,
                                    defaults={
                                        'task_name': task_data.get("name"),
                                        'task_status': task_data.get("status"),
                                        'description': task_data.get("description"),
                                        'source': json.dumps(task_data.get("source")),
                                    }
                                )

                print("Project, and tasks updated successfully.")
            except Project.DoesNotExist:
                print(f"Project with ID {project_id} does not exist.")
            except Exception as e:
                print(f"An error occurred: {str(e)}")


def update_profile_in_db(profile_data, user_id):
    if not user_id or not profile_data:
        return
    try:
        current_profile = Profile.objects.get(userid=user_id)

        if profile_data and current_profile:
            current_profile.email = profile_data.get('email', current_profile.email)
            current_profile.first_name = profile_data.get('name', current_profile.first_name)
            print("email: ", profile_data.get('email'))
            print("first_name: ", profile_data.get('name'))

            preferred_language = profile_data.get('preferred_language', {}).get('value')
            if preferred_language:
                print("preferred_language: ", preferred_language)
                if not current_profile.other_params:
                    current_profile.other_params = {}
                current_profile.other_params['preferred_language'] = preferred_language

            current_profile.org_associated = profile_data.get('organization', {}).get(
                'name', current_profile.org_associated)
            current_profile.designation = json.dumps(profile_data.get('user_roles', current_profile.designation))
            print("organization: ", profile_data.get('organization', {}).get('name'))
            print("designation: ",  json.dumps(profile_data.get('user_roles')))

            current_profile.save()

    except Profile.DoesNotExist:
        print(f"Profile with ID {user_id} does not exist.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
