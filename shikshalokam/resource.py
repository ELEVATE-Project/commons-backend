import json
from import_export import resources
from django.db import transaction, IntegrityError
from chatbot.models import Profile, Company
from chatbot.models.geo_models import ProfileAddress
from shikshalokam.models import ProjectStatus, TaskMandatoryStatus
from shikshalokam.models.project_models import (Project, Task, Evidence)
from shikshalokam.models.template_models import (Category, ProjectTemplate)
from import_export.results import Result
from import_export.fields import Field
from shikshalokam.scripts.template_ingestion import process_project_ingestion


class ProjectResource(resources.ModelResource):

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
    # sub_task_name_column_name = 'Sub-Tasks'
    # task_resource_name_column_name = 'Task Learning Resource Name'
    # task_resource_link_column_name = 'Task Learning Resource Link'
    task_evidence_column_name = 'Task Evidence'
    task_remarks_column_name = 'Task Remarks'

    project_id = Field(attribute='project_id', column_name=project_id_column_name)

    class Meta:
        model = Project
        import_id_fields = ('project_id',)
        fields = '__all__'

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        # print("Starting before_import")
        user_company = Company.objects.get(slug='shikshalokam')
        # programs_by_id = {program.program_id: program for program in Program.objects.all()}
        # programs_by_name = {program.title: program for program in Program.objects.all()}

        grouped_rows = {}
        for row in dataset.dict:
            project_id = row.get(self.project_id_column_name)
            if project_id not in grouped_rows:
                grouped_rows[project_id] = []
            grouped_rows[project_id].append(row)

        # print("Grouped rows by project_id:", len(grouped_rows))

        if dry_run:
            print("Dry run mode - No changes will be committed to the database.")
            return

        for project_id, project_rows in grouped_rows.items():
            if not project_id:
                # print(f"Skipping rows with missing project_id: {project_rows}")
                continue
            # print('Processing project ID:', project_id)
            # print('Number of rows:', len(project_rows))
            for project_row in project_rows:
                with transaction.atomic():
                    try:
                        first_name = project_row.get(self.UUID_column_name)
                        if not first_name or first_name == '':
                            print(f"Missing first_name for row: {project_row}")
                            raise ValueError("Missing first_name, rolling back transaction")
                        print('FIRST NAME: ', first_name)
                        designation = project_row.get(self.user_type_column_name)
                        other_params = {
                            'user_sub_type': project_row.get(self.user_sub_type_column_name),
                            'declared_board': project_row.get(self.declared_board_column_name)
                        }
                        org_associated = project_row.get(self.org_associated_column_name)

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
                                state=project_row.get(self.state_column_name),
                                district=project_row.get(self.district_column_name),
                                city=project_row.get(self.block_column_name),
                            )

                        category_name = project_row.get(self.category_name_column_name)
                        category_id = project_row.get(self.category_id_column_name)
                        category, _ = Category.objects.get_or_create(
                            name=category_name,
                            category_id=category_id
                        )
                        # Even if category is not there we will still create Project Template instance
                        template_title = project_row.get(self.template_title_column_name)
                        template_id = project_row.get(self.template_id_column_name)
                        description = project_row.get(self.template_description_column_name)
                        project_template, _ = ProjectTemplate.objects.get_or_create(
                            category=category,
                            title=template_title,
                            template_id=template_id,
                            description=description
                        )

                        project_title = project_row.get(self.title_column_name)
                        project_objective = project_row.get(self.objective_column_name)
                        project_duration = project_row.get(self.duration_column_name)
                        project_status = project_row.get(self.status_column_name)
                        project_recommended_for = project_row.get(self.recommended_for_column_name)
                        project_keywords = project_row.get(self.keywords_column_name)
                        project_resource_name = project_row.get(self.project_resource_name_column_name)
                        project_resource_link = project_row.get(self.project_resource_link_column_name)
                        if project_status:
                            project_status = project_status.strip().lower()
                            for status_choice in ProjectStatus.choices:
                                if project_status == status_choice[0].lower():
                                    project_status = status_choice[0]
                                    break
                        project_start_date = project_row.get(self.start_date_column_name)
                        project_end_date = project_row.get(self.end_date_column_name)
                        print(f"Creating/Updating Project for author: {author.id}, email: {author.email}")
                        print(f"Debug - Project ID: {project_id}, Project Row: {project_row}")
                        # program_name = project_row.get(self.program_name_column_name)
                        # program_id = project_row.get(self.program_id_column_name)
                        # program = None
                        # if program_id:
                        #     program = programs_by_id.get(program_id)
                        # elif program_name:
                        #     program = programs_by_name.get(program_name)
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
                            print(
                                f"Since project exist : Creating/Updating Project for author: {author.id}, email: {author.email}")
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

                        self.import_tasks(project_row, project)

                        print(f"Successfully processed row for project ID: {project_id}")

                    except IntegrityError as e:
                        print(f"IntegrityError in row for project ID: {project_id} - {str(e)}")
                    except Exception as e:
                        print(f"Error in row for project ID: {project_id} - {str(e)}")

        print("Import complete - Changes committed to the database.")

    def import_data(self, dataset, dry_run=False, raise_errors=False, **kwargs):
        return super().import_data(dataset, dry_run=False, raise_errors=raise_errors, **kwargs)

    def import_tasks(self, row, project):
        task_name = row.get(self.task_name_column_name)
        parent_task_id = row.get(self.task_id_column_name)
        task_id = row.get(self.task_id_column_name)
        mandatory_task = row.get(self.task_mandatory_task_column_name)
        observation_name = row.get(self.task_observation_name_column_name)
        number_of_submission_observation = row.get(self.task_number_of_submission_observation_column_name)
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
        self.import_evidence(row, task, project)

    def import_evidence(self, row, task, project):
        evidence_link_task = row.get(self.task_evidence_column_name)
        remark_task = row.get(self.task_remarks_column_name)

        evidence_link_project = row.get(self.project_evidence_column_name)
        remark_project = row.get(self.project_remarks_column_name)

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

class ExpertProjectResource(resources.ModelResource):
    class Meta:
        model = Project

    def import_data(self, dataset, dry_run=False, *args, **kwargs):
        json_list_data = dataset.dict
        if json_list_data and not isinstance(json_list_data, (list, dict)):
            json_list_data = json.loads(json_list_data)
        process_project_ingestion(json_list=json_list_data)

        result = Result()
        return result
