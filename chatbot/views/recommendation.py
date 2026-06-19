import os
from django.conf import settings
from jwt import ExpiredSignatureError, InvalidTokenError
from rest_framework.decorators import api_view
import requests
from django.http import JsonResponse
from chatbot.models import Profile
from chatbot.serializer.profile_serializer import ProfileSerializer
from chatbot.utils.profile_utils import create_profile_utils
from shikshalokam.models import Project, ProjectCreatedBy, ProjectVernacular
from shikshalokam.serializer import ProjectSerializer
import jwt
from shikshalokam.utils.recommendation_utils import get_expert_projects

recommendation_base_url = os.getenv("RECOMMENDATION_BASE_URL")
PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")



@api_view(["GET"])
def generate_recommendation(request):
    body = request.query_params
    limit = body.get("limit")
    page = body.get("page", 1)
    language = body.get("language")
    access_token = request.headers.get("X-auth-token")

    default_response = {
        'result': {
            "data": [],
            "count": 0
        }
    }

    try:
        decoded = jwt.decode(
        access_token,
        PUBLIC_KEY,
        algorithms=["HS256"]
        )
        user_id = decoded.get("data", {}).get("id")

        if not user_id:
            return JsonResponse(default_response, status=200, safe=False)
        
    except ExpiredSignatureError:
        return JsonResponse(default_response, status=200, safe=False)
    except InvalidTokenError:
        return JsonResponse(default_response, status=200, safe=False)

    try:
        res_profile = create_profile_utils(access_token=access_token)
        current_profile = Profile.objects.get(userid=user_id)
    except Profile.DoesNotExist:
        try:
            create_profile_utils(access_token=access_token)
            current_profile = Profile.objects.get(userid=user_id)
            print("Profile successfully created and retrieved.")
        except Profile.DoesNotExist:
            print("Failed to create or retrieve profile.")
            return JsonResponse(default_response, status=200, safe=False)
    
    try:
        current_profile_serialized = ProfileSerializer(current_profile).data
        project_templates = get_expert_projects(language=language)
        if not project_templates:
            return JsonResponse(default_response, status=200, safe=False)

        user_projects = Project.objects.filter(author=current_profile)
        user_projects_serialized = ProjectSerializer(user_projects, many=True).data

        data = {
            "current_profile": current_profile_serialized,
            "project_templates": project_templates,
            "user_projects": user_projects_serialized
        }
        url = recommendation_base_url
        response = requests.post(url, json=data)
        response.raise_for_status()

        results = response.json()
        matched_projects = []
        if results:
            matched_projects = results.get('matched_projects')
        count = len(matched_projects)

        if limit:
            page = int(page)
            limit = int(limit)
            print("limit: ", limit)
            print("page: ", page)
            start_index = (page - 1) * limit
            end_index = start_index + limit
            paginated_projects = matched_projects[start_index:end_index]
        else:
            paginated_projects = matched_projects

        return JsonResponse({
            'result': {
                "data": paginated_projects,
                "count": count
            }
        }, safe=False)
    except Exception as e:
        print(f"Error: {e}")
        return JsonResponse(default_response, status=200, safe=False)

