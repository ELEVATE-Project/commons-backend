import os
from jwt import ExpiredSignatureError, InvalidTokenError
from django.conf import settings
import traceback
import django_filters
from rest_framework import generics
from django.http import JsonResponse
from chatbot.models import Profile
from chatbot.utils.shikshalokam_mitra_utils import create_project_utils, import_project_from_library_utils
from shikshalokam.models import Project, Task, Evidence
from shikshalokam.scripts.template_ingestion import ingest_project_template, ingest_task_data
from shikshalokam.serializer import ProjectSerializer
from rest_framework.decorators import api_view
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.response import Response
import jwt
from rest_framework.exceptions import AuthenticationFailed

PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")

class ProjectListCreateView(generics.ListCreateAPIView):
    queryset = Project.objects.prefetch_related('task__evidence', 'evidence', 'learning_resource').select_related(
        'project_template__category', 'author'
    ).all()
    serializer_class = ProjectSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['id', 'project_id', 'program_id']


    def get_user_from_token(self, request):
        access_token = request.headers.get("X-auth-token")

        if not access_token:
            raise AuthenticationFailed("Access token missing")

        try:
            decoded = jwt.decode(
                access_token,
                PUBLIC_KEY,
                algorithms=["HS256"]
            )

            user_id = decoded.get("data", {}).get("id")

            if not user_id:
                raise AuthenticationFailed("Invalid token: user_id missing")

            return Profile.objects.get(userid=user_id)

        except ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired")

        except InvalidTokenError:
            raise AuthenticationFailed("Invalid token")

        except Profile.DoesNotExist:
            raise AuthenticationFailed("User not found")


    def list(self, request, *args, **kwargs):
        user = self.get_user_from_token(request)

        queryset = self.filter_queryset(self.get_queryset())

        if queryset.count() == 1:
            serializer = self.get_serializer(queryset.first(), context={'request': request, 'author': user})
            return Response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context={'request': request, 'author': user})
        return Response(serializer.data)


@api_view(['POST'])
@transaction.atomic
def duplicate_project_view(request):
    body = request.query_params

    project_template_id = request.data.get('projectTemplateId')
    program_name = request.data.get('programName')
    program_id = request.data.get('programId')
    project_id = body.get("id")

    access_token = request.headers.get("X-auth-token")

    try:
        decoded = jwt.decode(
            access_token,
            PUBLIC_KEY,
            algorithms=["HS256"]
        )
        user_id = decoded.get("data", {}).get("id")

        if not user_id:
            return JsonResponse({'message': "Invalid access token"}, status=401)

    except ExpiredSignatureError:
        return JsonResponse({'message': "Token expired"}, status=401)

    except InvalidTokenError:
        return JsonResponse({'message': "Invalid token"}, status=401)


    try:
        new_author = Profile.objects.get(userid=user_id)
    except Profile.DoesNotExist:
        return JsonResponse({'message': f"Profile not found for userid: {user_id}"}, status=404)

    try:
        original_project = Project.objects.prefetch_related('task__evidence').get(id=project_id)
        user_action_steps = [task.task_name for task in original_project.task.all()]

        if project_template_id:
            response = import_project_from_library_utils(
                access_token=access_token, program_name=program_name, project_template_id=project_template_id,
                program_id=program_id
            )
        else:
            if original_project.actual_problem_statement:
                user_problem_statement = original_project.actual_problem_statement
                project_title = original_project.actual_title
                project_duration_weeks = original_project.actual_duration
                project_objective = original_project.actual_objective
                print("Actual_duration_weeks: ", project_duration_weeks)
            else:
                user_problem_statement = original_project.expected_problem_statement
                project_title = original_project.expected_title
                project_duration_weeks = original_project.expected_duration
                project_objective = original_project.expected_objective
                print("Expected_duration_weeks: ", project_duration_weeks)
            print("project_duration_weeks: ", project_duration_weeks)
            response = create_project_utils(
                access_token=access_token, user_problem_statement=user_problem_statement,
                user_action_steps=user_action_steps, project_title=project_title,
                project_duration_weeks=project_duration_weeks, original_project=original_project,
                project_objective=project_objective, status='started'
            )

        print("response: ", response)
        if not response:
            return JsonResponse({'message': 'Error in Shikshalokam Project API'}, status=500, safe=False)

        temp_project_source = None
        if project_template_id:
            project_id = response.get('result', {}).get('_id')
            program_id = response.get('result', {}).get('programId')
            if original_project.template_id:
                temp_project_source = {
                    "projectTemplateId": original_project.template_id
                }
        else:
            project_id = response.get('projectId')
            program_id = response.get('programId')
            temp_project_source = response.get('chunks')

        print(f"project_id: {project_id}")
        print("Got Chunks: ", temp_project_source)
        if not project_id:
            return JsonResponse({'message': 'Error in Shikshalokam Project API'}, status=500, safe=False)

        duplicate_project, created = Project.objects.get_or_create(
            project_id=project_id,
            defaults={
                **{
                    field.name: getattr(original_project, field.name)
                    for field in Project._meta.fields
                    if field.name not in ['id', 'author', 'project_id', 'program_id', 'created_at', 'updated_at',
                                          'history', 'program_name', 'generated_by', 'project_source']
                },
                'program_id': program_id,
                'program_name': program_name,
                'author': new_author,
                'project_source': response.get('chunks')
            }
        )
        if created:
            for original_task in original_project.task.all():
                duplicate_task = Task.objects.create(
                    **{
                        field.name: getattr(original_task, field.name)
                        for field in Task._meta.fields
                        if field.name not in ['id', 'project', 'created_at', 'updated_at', 'history', 'created_by']
                    },
                    project=duplicate_project
                )

                for original_evidence in original_task.evidence.all():
                    Evidence.objects.create(
                        **{
                            field.name: getattr(original_evidence, field.name)
                            for field in Evidence._meta.fields
                            if field.name not in ['id', 'created_at', 'updated_at', 'history', 'created_by']
                        },
                        task=duplicate_task
                    )

        serialized_project = ProjectSerializer(duplicate_project).data
        print("Serialized project: ", serialized_project)
        if project_template_id:
            return JsonResponse(response, status=200, safe=False)
        else:
            return JsonResponse(response.get('original_response'), status=200, safe=False)

    except ObjectDoesNotExist:
        traceback.print_exc()

        return JsonResponse({'message': f"Project with id {project_id} does not exist."}, status=404, safe=False)

    except Exception as e:
        traceback.print_exc()

        return JsonResponse({
            'message': f"An error occurred while duplicating the project: {str(e)}"
        }, status=500, safe=False)


@api_view(['POST'])
def project_ingestion_view(request):
    body = request.data
    key = body.get('key')
    file_path = body.get('file_path')

    if key == 'TASK':
        ingest_task_data(file_path)
    elif key == 'PROJECT':
        ingest_project_template(file_path)

    return JsonResponse({
        'message': f"Done"
    }, status=200, safe=False)
