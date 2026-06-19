import traceback
import jwt
from django.http import JsonResponse

class VerifyAuthToken:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        auth_header = request.META.get('HTTP_AUTHORIZATION')

        AUTH_ERROR_MESSAGE = "Invalid token"
        
        if auth_header:
            # Trim "Bearer " prefix
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove "Bearer " (7 characters)
            else:
                return JsonResponse(
                    {'error': AUTH_ERROR_MESSAGE},
                    status=401
                )
            
            # Authenticate the JWT token
            try:
                # Decode the JWT token
                jwt.decode( token, options={"verify_signature": False})
                
            except jwt.ExpiredSignatureError:
                return JsonResponse(
                    {'error': AUTH_ERROR_MESSAGE},
                    status=401
                )
            except jwt.InvalidTokenError:
                return JsonResponse(
                    {'error': AUTH_ERROR_MESSAGE},
                    status=401
                )
            except Exception as e:
                traceback.print_exc()
                return JsonResponse(
                    {'error': f'Authentication failed'},
                    status=500
                )
        
        # If no Authorization header, allow the request to proceed
        response = self.get_response(request)
        return response