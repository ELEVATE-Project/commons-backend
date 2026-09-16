from rest_framework.decorators import api_view
from rest_framework.response import Response
from chatbot.utils.elevate.profile_utils import handle_elevate_profile


@api_view(['GET'])
def read_elevate_profile(request):
    access_token = request.headers.get('X-auth-token')
    print("Access token: ", access_token)

    if not access_token:
        return Response({
            'status': 'error',
            'message': 'Access token is required.'
        }, status=400)

    profile_details = handle_elevate_profile(access_token=access_token)

    if not profile_details or not profile_details.get('profileid'):
        return Response({
            'status': 'error',
            'message': 'Failed to fetch or create profile from Elevate.'
        }, status=500)

    return Response({
        'status': 'ok',
        'profile_details': profile_details
    }, status=200)
