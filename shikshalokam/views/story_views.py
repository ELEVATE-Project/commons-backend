import traceback

from rest_framework.decorators import api_view
from rest_framework.response import Response

from shikshalokam.utils.story_utils import create_story_object


@api_view(['POST'])
def create_story_from_project_view(request):
    try:
        profile_id = request.data['profile_id']
        model = request.data.get('model', None)
        if profile_id is None:
            response_json = create_story_object()
            return Response({
                'status': 'ok',
                'message': 'Story created For all projects',
                'response_json': response_json
            }, status=200)
        else:
            response_json = create_story_object(profile_id=profile_id, model_to_use=model)
            return Response({
                'status': 'ok',
                'message': f'Story created for profile_id: {profile_id}',
                'response_json': response_json
            }, status=200)
    except Exception as e:
        print(e)
        traceback.print_exc()
