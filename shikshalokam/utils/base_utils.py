import pandas as pd
from django.db import transaction, IntegrityError
from chatbot.models import Company, Profile, ProfileAddress
from shikshalokam.models import (Project, Task, Evidence, ProjectTemplate, ProjectStatus, Category, TaskMandatoryStatus)

program_name_column_name = 'Program Name'
program_id_column_name = 'Program ID'
UUID_column_name = 'UUID'
user_type_column_name = 'User Type'
user_sub_type_column_name = 'User sub type'
declared_board_column_name = 'Declared Board'
org_associated_column_name = 'Org Name'
state_column_name = 'Declared State'
district_column_name = 'District'
block_column_name = 'Block'
category_name_column_name = "Category"
category_id_column_name = "Category ID"
template_title_column_name = "Solution"
template_id_column_name = "Solution ID"
template_description_column_name = "Solution Description"
project_id_column_name = 'Project ID'
title_column_name = 'Project Title'
objective_column_name = 'Project Objective'
duration_column_name = 'Project Duration'
status_column_name = 'Project Status'
start_date_column_name = 'Project start date of the user'
end_date_column_name = 'Project completion date of the user'
recommended_for_column_name = 'recommendedFor'
keywords_column_name = 'keywords'
project_resource_name_column_name = 'Project Learning Resource Name'
project_resource_link_column_name = 'Project Learning Resource Link'
project_evidence_column_name = 'Project Evidence'
project_remarks_column_name = 'Project Remarks'
task_name_column_name = 'Tasks'
task_id_column_name = 'Task ID'
task_mandatory_task_column_name = 'Task Status'
task_observation_name_column_name = 'Observation'
task_number_of_submission_observation_column_name = 'Number of submission'
task_evidence_column_name = 'Task Evidence'
task_remarks_column_name = 'Task Remarks'


def upload_csv_to_db(file_path='shikshalokam/utils/shikshalokamTest.csv', start_index=0, end_index=None):
    df = pd.read_csv(file_path, on_bad_lines='skip')

    user_company = Company.objects.get(slug='shikshalokam')
    grouped_rows = list(df.groupby(project_id_column_name))
    total_projects = len(grouped_rows)

    if end_index is None or end_index > total_projects:
        end_index = total_projects

    for i in range(start_index, end_index):
        project_id, group = grouped_rows[i]
        try:
            with transaction.atomic():
                for index, row in group.iterrows():
                    first_name = row.get(UUID_column_name)
                    if not first_name or first_name == '':
                        print(f"Missing first_name for row: {row}")
                        raise ValueError("Missing first_name, rolling back transaction")
                    print('FIRST NAME: ', first_name)

                    designation = row.get(user_type_column_name)
                    other_params = {
                        'user_sub_type': row.get(user_sub_type_column_name),
                        'declared_board': row.get(declared_board_column_name)
                    }
                    org_associated = row.get(org_associated_column_name)

                    user_email = '{}@{}.com'.format(first_name, 'shikshalokam')
                    if not user_company or not user_email:
                        print(f"Invalid company or email for first_name: {first_name}")
                        continue
                    print(f"Fetching/Creating Profile for email: {user_email}")

                    author, author_created = Profile.objects.get_or_create(
                        email=user_email, company=user_company,
                        defaults={
                            'first_name': first_name,
                            'designation': designation,
                            'other_params': other_params,
                            'org_associated': org_associated,
                        }
                    )
                    print(f"Profile created: {author_created}, Profile ID: {author.id if author else 'None'}")
                    if author_created:
                        ProfileAddress.objects.create(
                            profile=author,
                            state=row.get(state_column_name),
                            district=row.get(district_column_name),
                            city=row.get(block_column_name),
                        )

                    category_name = row.get(category_name_column_name)
                    category_id = row.get(category_id_column_name)
                    category, _ = Category.objects.get_or_create(
                        name=category_name,
                        category_id=category_id
                    )

                    template_title = row.get(template_title_column_name)
                    template_id = row.get(template_id_column_name)
                    description = row.get(template_description_column_name)
                    project_template, _ = ProjectTemplate.objects.get_or_create(
                        category=category,
                        title=template_title,
                        template_id=template_id,
                        description=description
                    )

                    project_title = row.get(title_column_name)
                    project_objective = row.get(objective_column_name)
                    project_duration = row.get(duration_column_name)
                    project_status = row.get(status_column_name)
                    if project_status:
                        project_status = project_status.strip().lower()
                        for status_choice in ProjectStatus.choices:
                            if project_status == status_choice[0].lower():
                                project_status = status_choice[0]
                                break
                    project_start_date = row.get(start_date_column_name)
                    project_end_date = row.get(end_date_column_name)
                    project_recommended_for = row.get(recommended_for_column_name)
                    project_keywords = row.get(keywords_column_name)
                    project_resource_name = row.get(project_resource_name_column_name)
                    project_resource_link = row.get(project_resource_link_column_name)
                    print(f"Creating/Updating Project for author: {author.id}, email: {author.email}")
                    print(f"Debug - Project ID: {project_id}, Project Row: {row}")

                    project, created = Project.objects.get_or_create(
                        project_id=project_id,
                        defaults={
                            'project_template': project_template,
                            'author': author,
                            'title': project_title,
                            'objective': project_objective,
                            'duration': project_duration,
                            'project_status': project_status,
                            'project_start_date': project_start_date,
                            'project_end_date': project_end_date,
                            'recommended_for': project_recommended_for,
                            'keywords': project_keywords,
                            'resource_name': project_resource_name,
                            'resource_link': project_resource_link
                        }
                    )
                    print(f"Project created: {created}, Project ID: {project.id if project else 'None'}")

                    if not created:
                        print(f"Project already exists. Updating Project ID: {project_id}")
                        project.project_template = project_template
                        project.author = author
                        project.title = project_title
                        project.objective = project_objective
                        project.duration = project_duration
                        project.project_status = project_status
                        project.project_start_date = project_start_date
                        project.project_end_date = project_end_date
                        project.recommended_for = project_recommended_for
                        project.keywords = project_keywords
                        project.resource_name = project_resource_name
                        project.resource_link = project_resource_link
                        project.save()

                    import_tasks_and_related_data(row, project)

            print(f"Successfully processed rows for project ID: {project_id}")

        except IntegrityError as e:
            print(f"IntegrityError in rows for project ID: {project_id} - {str(e)}")
        except Exception as e:
            print(f"Error in rows for project ID: {project_id} - {str(e)}")


def import_tasks_and_related_data(row, project):
    task_name = row.get(task_name_column_name)
    parent_task_id = row.get(task_id_column_name)
    task_id = row.get(task_id_column_name)
    mandatory_task = row.get(task_mandatory_task_column_name)
    observation_name = row.get(task_observation_name_column_name)
    number_of_submission_observation = row.get(task_number_of_submission_observation_column_name)
    if mandatory_task:
        mandatory_task = mandatory_task.strip().lower()
        for task_choice in TaskMandatoryStatus.choices:
            if mandatory_task == task_choice[0].lower():
                mandatory_task = task_choice[0]
                break
    task, _ = Task.objects.get_or_create(
        project=project,
        defaults={
            'task_name': task_name,
            'parent_task_id': parent_task_id,
            'task_id': task_id,
            'mandatory_task': mandatory_task,
            'observation_name': observation_name,
            'number_of_submission_observation': number_of_submission_observation
        }
    )
    import_evidence(row, task, project)


def import_evidence(row, task, project):
    evidence_link_task = row.get(task_evidence_column_name)
    remark_task = row.get(task_remarks_column_name)

    evidence_link_project = row.get(project_evidence_column_name)
    remark_project = row.get(project_remarks_column_name)

    if evidence_link_project:
        Evidence.objects.get_or_create(
            project=project,
            evidence_link=evidence_link_project,
            remark=remark_project
        )

    if evidence_link_task:
        Evidence.objects.get_or_create(
            task=task,
            evidence_link=evidence_link_task,
            remark=remark_task
        )
