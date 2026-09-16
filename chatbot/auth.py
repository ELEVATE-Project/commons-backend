import traceback
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.apps import apps as django_apps
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings
from chatbot.models.auth_models import BlacklistedToken


class ProfileJWTAuthentication(JWTAuthentication):

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.user_model = django_apps.get_model('chatbot.Profile', require_ready=False)

    def get_user(self, validated_token):
        """
        Attempts to find and return a user using the given validated token.
        """
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken(_("Token contained no recognizable user identification"))

        try:
            user = self.user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        return user

    def authenticate(self, request):
        try:
            if 'Authorization' not in request.headers:
                raise AuthenticationFailed('Token not found')

            authentication = super().authenticate(request)
            print(authentication)
            if authentication:
                token = authentication[1]
                print(token)
                # Check if the token is blacklisted
                if BlacklistedToken.objects.filter(token=token).exists():
                    print('Token blacklisted')
                    raise AuthenticationFailed('Invalid token.')

                return authentication
            else:
                print('Token not authenticated')
        except AuthenticationFailed as e:
            print(e)
            traceback.print_exc()
            raise e
        except Exception as e:
            print(e)
            traceback.print_exc()
            return None
