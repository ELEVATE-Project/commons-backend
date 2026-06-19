import json
from shikshalokam.models import Project, ProjectCreatedBy, ProjectVernacular
from shikshalokam.serializer import ProjectSerializer


def get_expert_projects(language):
    try:
        print("Here")
        projects = Project.objects.filter(generated_by=ProjectCreatedBy.EXPERT_VETTED)
        project_serialized = ProjectSerializer(projects, many=True).data
        for project in project_serialized:
            project_id = project.get('project_id')
            if project['generated_by'] == ProjectCreatedBy.EXPERT_VETTED:
                print("language: ", language)
                vernacular = ProjectVernacular.objects.filter(
                    project__project_id=project['project_id'], language=language
                ).first()
                print("vernacular: ", vernacular)
                if vernacular:
                    if 'other_params' not in project:
                        project['other_params'] = {}
                    print("Going for project id: ", project_id)
                    vernacular_details = json.loads(vernacular.details)
                    project['actual_title'] = vernacular_details.get('title')
                    project['description'] = vernacular_details.get('description')
                    project['categories'] = vernacular_details.get('categories')
                    project['recommendedFor'] = vernacular_details.get('recommendedFor')
                    project['actual_problem_statement'] = vernacular_details.get('problemStatement')
                    project['other_params']['text'] = vernacular_details.get('text')
                    project['other_params']['impact'] = vernacular_details.get('impact')
                    project['other_params']['summary'] = vernacular_details.get('summary')
                    project['other_params']['template_author'] = vernacular_details.get('template_author')

        return project_serialized
    except Exception as e:
        print("Error: ", e)
        return None
