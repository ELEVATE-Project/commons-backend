from rest_framework.decorators import api_view
from rest_framework.response import Response

from chatbot.utils.elevate.profile_utils import handle_elevate_profile
from chatbot.utils.profile_utils import create_profile_utils


@api_view(['POST'])
def create_profile_views(request):
    body = request.data
    access_token = body.get('access_token')
    print("Access token: ", access_token)

    if not access_token:
        return Response({
            'status': 'error',
            'message': 'Access token is required.'
        }, status=400)

    profile_details = create_profile_utils(access_token=access_token)

    if not profile_details.get('success'):
        return Response({
            'status': 'error',
            'message': profile_details.get('message', 'Failed to fetch or create profile details.')
        }, status=profile_details.get('status_code', 500))

    return Response({
        'status': 'ok',
        'profile_details': profile_details.get('data')
    }, status=200)


# @api_view(['GET'])
# def read_elevate_profile(request):
#     access_token = request.headers.get('X-auth-token')
#     print("Access token: ", access_token)

#     if not access_token:
#         return Response({
#             'status': 'error',
#             'message': 'Access token is required.'
#         }, status=400)

#     profile_details = handle_elevate_profile(access_token=access_token)

#     if not profile_details or not profile_details.get('profileid'):
#         return Response({
#             'status': 'error',
#             'message': 'Failed to fetch or create profile from Elevate.'
#         }, status=500)

#     return Response({
#         'status': 'ok',
#         'profile_details': profile_details
#     }, status=200)
