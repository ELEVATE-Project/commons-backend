from chatbot.models import Story, StoryMedia, SessionFlowName
from chatbot.models.base_models import Flow
from chatbot.models.enums import CreateStoryChoices
from chatbot.models.media_models import ProfileMedia
from chatbot.serializer.profile_serializer import ProfileMediaSerializer
from chatbot.serializer.story_serializer import StoryCreateSerializer, StoryRetrieveSerializer, StoryMediaRetrieveSerializer, StoryFullSerializer
from chatbot.utils.recreate_story_utils import re_create_story_object
from chatbot.utils.shikshalokam_story_utils import update_story_pdf
from chatbot.utils.story_utils.base.story_update_utils import extract_update_data, get_or_create_translation, update_translation_fields, sync_to_main_story
from chatbot.utils.story_utils.base.translation_mixins import LanguageDetectionMixin
from chatbot.utils.story_utils.story_utils import create_story_object, generate_story
from django.contrib.auth import PermissionDenied
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
import django_filters
import traceback
import logging

logger = logging.getLogger('django')


@api_view(['POST'])
def end_story(request):
    error_type='generic_error'
    try:
        profile_id = request.data['profile_id']
        session = request.data['session']
        model = request.data.get('model', None)
        access_token = request.data.get('access_token', None)
        flow = request.data.get('flow')
        language = request.data.get('language', 'en')

        if session is None:
            return Response({
                'status': 'error',
                'message': 'session is mandatory',
                'error_message': 'session is mandatory',
                'error_type': error_type,
            }, status=400)
        else:
            id, content, error_msg, error_type = create_story_object(
                profile_id=profile_id, session=session,
                access_token=access_token, flow=flow, language=language
            )

            if error_msg:
                return Response({
                    'status': 'error',
                    'message': error_msg,
                    'error_message': error_msg,
                    'error_type': error_type,
                }, status=400)

            return Response({
                'status': 'ok',
                'message': 'Story created',
                'id': id,
                'content': content,
            }, status=200)
    except Exception as e:
        traceback.print_exc()
        return Response({
            'status': 'error',
            'message': '',
            'error_message': f'{e}',
            'error_type': error_type,
        }, status=500)


@api_view(['POST'])
def end_story_v2(request):
    error_type='generic_error'
    try:
        profile_id = request.data['profile_id']
        session = request.data['session']
        access_token = request.headers.get('Authorization', "Bearer: ")[7:]
        flow = request.data.get('flow')
        language = request.data.get('language', 'en')

        if isinstance(access_token, str):
            access_token = access_token.strip()
            if access_token == "":
                access_token = None

        if session is None:
            return Response({
                'status': 'error',
                'message': 'session is mandatory',
                'error_message': 'session is mandatory',
                'error_type': error_type
            }, status=400)

        id, content, error_msg, error_type = generate_story(
            profile_id=profile_id, session=session,
            access_token=access_token, flow=flow, language=language
        )
        if error_msg:
            return Response({
                'status': 'error',
                'message': error_msg,
                'error_message': error_msg,
                'error_type': error_type,
            }, status=400)

        return Response({
            'status': 'ok',
            'message': 'Story created',
            'id': id,
            'content': content,
        }, status=200)
    except Flow.DoesNotExist:
        return Response({
            'status': 'error',
            'message': '',
            'error_message': "Invalid flow",
            'error_type': error_type
        }, status=404)

    except Exception as e:
        traceback.print_exc()
        return Response({
            'status': 'error',
            'message': '',
            'error_message': f'{e}',
            'error_type': error_type
        }, status=500)


class StoryListCreateView(generics.ListCreateAPIView):
    queryset = Story.objects.all()
    serializer_class = StoryCreateSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['session', 'author']


class StoryRetrieveUpdateDestroyView(LanguageDetectionMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Story.objects.all()
    serializer_class = StoryRetrieveSerializer


    def partial_update(self, request, *args, **kwargs):
        print("Updating (PATCH)")

        story = self.get_object()
        language = self.detect_language(request, story)

        if language != 'en':
            return self.handle_translation_update(request, language, *args, **kwargs)
        else:
            return self.handle_update_logic(request, *args, **kwargs, is_partial=True)

    def handle_translation_update(self, request, language, *args, **kwargs):
        """Handle updates to story translations AND sync back to main story"""
        story = self.get_object()

        try:
            # Step 1: Extract and validate request data
            update_data = extract_update_data(request)
            print("update_data: ", update_data)
            # Step 2: Get or create translation
            translation = get_or_create_translation(story, language, update_data)
            print("translation: ", translation)

            # Step 3: Update translation with new data
            update_translation_fields(translation, update_data, language)
            print("update_translation_fields done")

            # Step 4: Sync back to main story (English)
            sync_to_main_story(story, translation, update_data, language)
            print("sync_to_main_story done")

            # Step 5: Generate response and handle post-update tasks
            return self._generate_update_response(request, story, update_data)

        except Exception as e:
            print(f"Error while handle_translation_update {e}")
            return self._handle_update_error(e)

    def _generate_update_response(self, request, story, update_data):
        """Generate response and handle post-update tasks"""
        # Generate serialized response
        serializer = self.get_serializer(story, context={'request': request})
        response_data = serializer.data

        # Handle PDF update if needed
        if update_data.get('session') and update_data.get('flow'):
            update_story_pdf(
                access_token=update_data['access_token'],
                session=update_data['session'],
                flow=update_data['flow'],
                is_edit_story=True
            )

        return Response(response_data, status=status.HTTP_200_OK)

    def _handle_update_error(self, error):
        """Handle update errors consistently"""
        print(f"Error updating translation: {str(error)}")
        traceback.print_exc()
        return Response({
            'error': f'Failed to update translation: {str(error)}'
        }, status=status.HTTP_400_BAD_REQUEST)


    def handle_update_logic(self, request, *args, **kwargs):
        """Handle English story updates"""
        is_partial = kwargs.pop('is_partial', False)
        session_value = request.data.get('session')
        access_token = request.data.get('access_token')
        flow = request.data.get('flow')

        try:
            if is_partial:
                response = super().partial_update(request, *args, **kwargs)
                if response and response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]:
                    update_story_pdf(
                        access_token=access_token, session=session_value, flow=flow,
                        is_edit_story=True
                    )
                return response
        except Exception as e:
            print("Error occurred: ", str(e))
            raise


class StoryMediaListCreateView(generics.ListCreateAPIView):
    queryset = StoryMedia.objects.all()
    serializer_class = StoryMediaRetrieveSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['story']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        """
        Handle POST requests (create).
        """
        print("Creating")
        session_value = request.data.get('session')
        access_token = request.data.get('access_token')
        flow = request.data.get('flow')
        file_url = request.data.get('file_url')

        if file_url is not None and file_url.startswith("s3://"):
            file_url = "https://" + file_url[len("s3://"):]
            request.data["file_url"] = file_url

        print("session_value: ", session_value)
        print("flow: ", flow)
        print("access_token: ", access_token)
        try:
            response = super().create(request, *args, **kwargs)
            print("response: ", response)
            print("response status_code: ", response.status_code)

            if response.status_code == status.HTTP_201_CREATED and flow != SessionFlowName.Reflection:
                update_story_pdf(
                    access_token=access_token, session=session_value, flow=flow
                )
            return response

        except Exception as e:
            logger.error("Error: %s", e, exc_info=True)
            raise


class StoryMediaRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StoryMedia.objects.all()
    serializer_class = StoryMediaRetrieveSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def partial_update(self, request, *args, **kwargs):
        """
        Handle PATCH requests for partial updates.
        """
        print("Updating (PATCH)")
        return self.handle_update_logic(request, *args, **kwargs, is_partial=True)

    def update(self, request, *args, **kwargs):
        """
        Handle PUT requests for full updates.
        """
        print("Updating (PUT)")
        return self.handle_update_logic(request, *args, **kwargs, is_partial=False)

    def handle_update_logic(self, request, *args, **kwargs):
        """
        Shared logic for PUT and PATCH requests.
        """
        is_partial = kwargs.pop('is_partial', False)  # Safely extract the flag
        session_value = request.data.get('session')
        access_token = request.data.get('access_token')
        flow = request.data.get('flow')
        print("session_value: ", session_value)
        print("flow: ", flow)
        print("access_token: ", access_token)

        try:
            if is_partial:
                response = super().partial_update(request, *args, **kwargs)
            else:
                response = super().update(request, *args, **kwargs)

            print("response: ", response)
            print("response status_code: ", response.status_code)

            if (response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT] and
                    flow != SessionFlowName.Reflection):
                    update_story_pdf(
                        access_token=access_token, session=session_value, flow=flow
                    )
            return response
        except Exception as e:
            print("Error occurred: ", str(e))
            raise


class ProfileMediaListCreateView(generics.ListCreateAPIView):
    queryset = ProfileMedia.objects.all()
    serializer_class = ProfileMediaSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['profile']

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class ProfileMediaRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProfileMedia.objects.all()
    serializer_class = ProfileMediaSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


@api_view(['POST'])
def story_recreate_view(request):
    profile_id = request.data.get('profile_id')
    session_id = request.data.get('session_id')
    print('profile_id: ', profile_id)
    print('session_id: ', session_id)
    if profile_id is None or session_id is None:
        return Response({'error': 'Profile ID and Session ID are required.'}, status=status.HTTP_400_BAD_REQUEST)

    story_id, story_content = re_create_story_object(profile_id, session_id)
    temp_json = {
        'id': story_id,
        'content': story_content
    }

    return Response({'message': temp_json}, status=status.HTTP_200_OK)


class StoryBySessionView(generics.ListAPIView):
    serializer_class = StoryFullSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['session']

    def get_queryset(self):
        session_id = self.request.query_params.get('session')
        if session_id:
            return Story.objects.filter(session=session_id)
        return Story.objects.none()
