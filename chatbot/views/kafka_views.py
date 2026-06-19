from rest_framework.decorators import api_view
from django.http import JsonResponse
from chatbot.utils.kafka_utils import update_profile_in_db, update_project_in_db


@api_view(["POST"])
def sync_user_project_view(request):
    body = request.data
    user_id = body.get("userId")
    if isinstance(user_id, str):
        user_id = int(user_id)
    profile_data = body.get("profile")
    project_data = body.get("projects")

    try:
        update_profile_in_db(profile_data=profile_data, user_id=user_id)
        update_project_in_db(project_data=project_data)

        return JsonResponse({
            "message": "Data updated successfully.",
            "status": "success",
        }, status=200)

    except Exception as e:
        print("Error: ", e)
        return JsonResponse({
            "message": f"An unexpected error occurred: {str(e)}",
            "status": "error",
        }, status=500)
