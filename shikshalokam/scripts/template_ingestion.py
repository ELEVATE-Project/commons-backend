import json
from django.db import transaction

from chatbot.models import Profile, Company
from chatbot.models.geo_models import ProfileAddress
from shikshalokam.models import Project, Evidence, ProjectCreatedBy, LearningResources, Task
from shikshalokam.models.project_vernacular_model import ProjectVernacular


def ingest_project_template(file_path):
    # file_path = 'shikshalokam/scripts/projectTemplateJson.json'
    json_data = load_json(file_path)
    results = json_data

    if not results:
        print("No projects found in the provided JSON file.")
        return

    try:
        process_project_ingestion(json_list=results)
    except Exception as e:
        print(f"Error during project ingestion: {e}")


def ingest_task_data(file_path):
    # file_path = 'shikshalokam/scripts/TemplateTask.json'
    json_data = load_json(file_path)
    results = json_data

    if not results:
        print("No tasks found in the provided JSON file.")
        return

    try:
        with transaction.atomic():
            task_dict = {}
            missing_project_tasks = []

            for task_data in results:
                project_id = task_data.get('projectTemplateId')
                try:
                    project = Project.objects.get(project_id=project_id)
                except Project.DoesNotExist:
                    print(
                        f"Project with project_id '{project_id}' does not exist. Skipping task "
                        f"'{task_data.get('name')}'.")
                    missing_project_tasks.append(project_id)
                    continue

                task, task_created = Task.objects.get_or_create(
                    project=project,
                    task_id=task_data.get('_id'),
                    defaults={
                        "task_name": task_data.get('name'),
                        "description": task_data.get('description'),
                        "other_params": {
                            'solution_details': task_data.get('solutionDetails', {}),
                            'task_sequence': task_data.get('taskSequence', {}),
                        },
                    }
                )

                task_dict[task_data.get('_id')] = task

                if task_created:
                    print(f"Task '{task.task_name}' created successfully.")
                else:
                    print(f"Task '{task.task_name}' already exists.")

                translations = task_data.get('translations', {})
                for language, details in translations.items():
                    vernacular, vernacular_created = ProjectVernacular.objects.get_or_create(
                        task=task,
                        language=language,
                        defaults={
                            "details": json.dumps(details)
                        }
                    )
                    if vernacular_created:
                        print(f"Translation for language '{language}' saved for task '{task.task_name}'.")
                    else:
                        vernacular.details = json.dumps(details)
                        vernacular.save()
                        print(f"Translation for language '{language}' updated for task '{task.task_name}'.")

            for task_data in results:
                parent_task = task_dict.get(task_data.get('_id'))

                if 'children' in task_data and parent_task:
                    for child_task_id in task_data['children']:
                        if child_task_id in task_dict:
                            child_task = task_dict[child_task_id]
                            child_task.parent_task_id = parent_task.task_id
                            child_task.save()
                            print(f"Assigned parent_task_id '{parent_task.task_id}' "
                                  f"to child task '{child_task.task_id}'.")
            if missing_project_tasks:
                print("Tasks with missing projects: ", missing_project_tasks)

    except Exception as e:
        print(f"Error during task ingestion: {e}")



def load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


def process_project_ingestion(json_list):
    try:
        with transaction.atomic():
            for result in json_list:

                try:
                    author_detail = result.get('author')
                    # if not author_detail:
                        # raise ValueError("Author detail is missing")
                    if author_detail:
                        name, location = map(str.strip, author_detail.split(",", 1))
                        email = (result.get('_id') or "") + "@shikshalokam.org"
                        company = Company.objects.filter(slug='shikshalokamstaging').first()
                        profile, profile_created = Profile.objects.update_or_create(
                            email=email,
                            defaults={
                                "first_name": name,
                                "company": company,
                                "password": 'grit@123',
                            }
                        )
                        if profile_created:
                            print(f"Profile '{profile.id}' created successfully.")
                        else:
                            print(f"Profile '{profile.id}' already exists.")

                        ProfileAddress.objects.update_or_create(
                            profile=profile,
                            defaults={
                                "state": location
                            }
                        )
                    else:
                        profile = None
                except Exception as e:
                    print("Profile error: ", e)
                    profile = None

                project, created = Project.objects.get_or_create(
                    project_id=result.get('_id'),
                    defaults={
                        "author": profile,
                        "template_id": result.get('_id'),
                        "description": result.get('description'),
                        "keywords": json.dumps(result.get('keywords')),
                        "recommended_for": json.dumps(result.get('recommendedFor')),
                        "actual_title": result.get('title'),
                        "categories": json.dumps(result.get('categories')),
                        "actual_duration": result.get('metaInformation', {}).get('duration', None),
                        "actual_problem_statement": result.get('problemStatement'),
                        "program_id": result.get('programId'),
                        "other_params": {
                            'text': result.get('text'),
                            'impact': result.get('impact'),
                            'summary': result.get('summary'),
                            'template_author': result.get('author'),
                        },
                        "project_status": result.get('status', '').upper(),
                        "generated_by": ProjectCreatedBy.EXPERT_VETTED
                    }
                )

                if created:
                    print(f"Project '{project.actual_title}' created successfully.")
                else:
                    print(f"Project '{project.actual_title}' already exists.")

                evidences = result.get('evidences', [])
                for evidence_data in evidences:
                    evidence, evidence_created = Evidence.objects.get_or_create(
                        project=project,
                        evidence_link=evidence_data.get('link'),
                        remark=evidence_data.get('title'),
                        defaults={
                            "type": evidence_data.get('type')
                        }
                    )
                    if evidence_created:
                        print(f"Evidence '{evidence.remark}' saved for project '{project.actual_title}'.")
                    else:
                        print(f"Evidence '{evidence.remark}' already exists for project '{project.actual_title}'.")

                learning_resources = result.get('learningResources', [])
                for lr_data in learning_resources:
                    lr, lr_created = LearningResources.objects.get_or_create(
                        project=project,
                        link=lr_data.get('link'),
                        name=lr_data.get('name'),
                        defaults={
                            "resource_id": lr_data.get('id'),
                            "app": lr_data.get('app')
                        }
                    )
                    if lr_created:
                        print(f"Learning resource '{lr.name}' saved for project '{project.actual_title}'.")
                    else:
                        print(f"Learning resource '{lr.name}' already exists for project '{project.actual_title}'.")

                translations = result.get('translations', {})
                for language, details in translations.items():
                    vernacular, vernacular_created = ProjectVernacular.objects.get_or_create(
                        project=project,
                        language=language,
                        defaults={
                            "details": json.dumps(details)
                        }
                    )
                    if vernacular_created:
                        print(f"Translation for language '{language}' saved for project '{project.actual_title}'.")
                    else:
                        vernacular.details = json.dumps(details)
                        vernacular.save()
                        print(f"Translation for language '{language}' updated for project '{project.actual_title}'.")
    except Exception as e:
        print(f"Error during project ingestion: {e}")
        raise