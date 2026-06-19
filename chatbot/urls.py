from chatbot.utils.image_converter import convert_image
from chatbot.views.Media.extract_views import BatchMediaExtractView, BatchMediaRetryExtractView
from chatbot.views.Media.media_tracking_views import MediaViewTrackAPIView, MediaDownloadTrackAPIView, \
    SolutionDownloadTrackView
from chatbot.views.Media.save_views import BatchMediaSaveView, BatchMediaRetrySaveView
from chatbot.views.Media.status_views import BatchMediaTaskStatusView, VectorDBTaskStatusView
from chatbot.views.Media.upload_views import BatchMediaUploadView

from chatbot.views.Media.document_upload_view import DocumentUploadView 
from chatbot.views.admin.generic_upload_views import GenericBatchUploadView, GenericBatchTemplateView, \
    GenericBatchImportView
from chatbot.views.aws_views import get_presigned_url
from chatbot.views.gotenberg_view import generate_pdf_view, generate_pdf_view_v2
from chatbot.views.kafka_views import sync_user_project_view
from chatbot.views.location_views import get_location_view, get_ip_location_view
from chatbot.views.Media.media_views import MediaSearchView
from chatbot.views.Media.media_api_views import FetchThemeView, MediaSearchV2View
from chatbot.views.profile_views import create_profile_views
from django.urls import path, include
from chatbot.views import api_views
from chatbot.views.bhashini_views import text_speech_view, speech_text, text_translation_view, text_transliterate_view
from chatbot.views.chat_view import save_chats_view, create_chatsession, save_ptm_chats
from chatbot.views.drf_views import CompanyChatListCreateView, CompanyChatRetrieveUpdateDestroyView, \
    CompanyBotListCreateView, CompanyBotRetrieveUpdateDestroyView, ProfileListCreateView, \
    ProfileRetrieveUpdateDestroyView, ChatSessionListCreateView, ChatSessionRetrieveUpdateDestroyView, \
    ChatSessionRetrieveUpdateDestroyViewSession, BotVernacularListCreateView, BotVernacularRetrieveUpdateDestroyView, \
    FlowImageConfigView, FlowLanguagesView, FlowConnectionInfoView
from chatbot.views.mitra_views import \
    create_project_view
from chatbot.views.recommendation import generate_recommendation
from chatbot.views.story_views import end_story, end_story_v2, StoryListCreateView, StoryBySessionView, \
    StoryRetrieveUpdateDestroyView, StoryMediaListCreateView, StoryMediaRetrieveUpdateDestroyView
from rest_framework.routers import DefaultRouter
from chatbot.views.Media.media_api_views import MediaViewSet
from chatbot.views.Media import google_drive_integration

app_name = "chatbot"

router = DefaultRouter()
router.register(r'media', MediaViewSet, basename='media')


urlpatterns = [
    path('api/profile/', api_views.post_profile),
    path('api/user_profile/', ProfileListCreateView.as_view(), name='profile-list-create'),

    path('api/generate-session/', api_views.generate_session_id, name='generate_session_id'),
    path('api/login/', api_views.login, name='login'),
    path('api/logout/', api_views.logout, name='logout'),

    path('api/end-story/', end_story, name='end-story'),
    path('api/end-story/v2/', end_story_v2, name='end-story-v2'),

    path('api/text_to_speech/', text_speech_view, name='text_speech_view'),
    path('api/asr/', speech_text, name='speech_text'),
    path('api/text_translate/', text_translation_view, name='text_translation_view'),
    path('api/text_transliterate/', text_transliterate_view, name='text_transliterate_view'),

    path('api/companychat/', CompanyChatListCreateView.as_view(), name='companychat-list-create'),
    path('api/companychat/<int:pk>/', CompanyChatRetrieveUpdateDestroyView.as_view(),
         name='companychat-retrieve-update-destroy'),

    path('api/companybot/', CompanyBotListCreateView.as_view(), name='companybot-list-create'),
    path('api/companybot/<int:pk>/', CompanyBotRetrieveUpdateDestroyView.as_view(),
         name='companybot-retrieve-update-destroy'),

    path('api/bot_vernacular/', BotVernacularListCreateView.as_view(), name='bot_vernacular-list-create'),
    path('api/bot_vernacular/<int:pk>/', BotVernacularRetrieveUpdateDestroyView.as_view(),
         name='bot_vernacular-retrieve-update-destroy'),

    path('api/story/', StoryListCreateView.as_view(), name='story-list-create'),
    path('api/get-story/', StoryBySessionView.as_view(), name='story-by-session'),
    path('api/story/<int:pk>/', StoryRetrieveUpdateDestroyView.as_view(),
         name='story-retrieve-update-destroy'),
    # path('api/story-re-create/', story_recreate_view, name='story_recreate_view'),

    path('api/storymedia/', StoryMediaListCreateView.as_view(), name='story-media-list-create'),
    path('api/storymedia/<int:pk>/', StoryMediaRetrieveUpdateDestroyView.as_view(),
         name='story-media-retrieve-update-destroy'),

    path('api/profileuser/', ProfileListCreateView.as_view(), name='profile-user-list-create'),
    path('api/profileuser/<int:pk>/', ProfileRetrieveUpdateDestroyView.as_view(),
         name='profile-user-retrieve-update-destroy'),

    path('api/chatsession/', ChatSessionListCreateView.as_view(), name='chatsession-list-create'),
    path('api/chatsession/<int:pk>/', ChatSessionRetrieveUpdateDestroyView.as_view(),
         name='chatsession-retrieve-update-destroy'),
    path('api/chatsession/<str:session>/', ChatSessionRetrieveUpdateDestroyViewSession.as_view(),
         name='chatsession-retrieve-update-destroy'),

    # Flow APIs
    path('api/flow-image-config/', FlowImageConfigView.as_view(), name='flow-image-config'),
    path('api/flow-languages/', FlowLanguagesView.as_view(), name='flow-languages'),
    path('api/flow-connection-info/', FlowConnectionInfoView.as_view(), name='flow-connection-info'),

    path('api/save-company-chat/', save_chats_view, name="save-company-chat"),
    path('api/create-chatsession/', create_chatsession, name="create-chatsession"),
    path('api/create-profile/', create_profile_views, name="create-profile"),
    path('api/create-project/', create_project_view, name="create-project"),
    path('api/generate-pdf/', generate_pdf_view, name='generate_pdf'),
    path('api/generate-pdf/v2/', generate_pdf_view_v2, name='generate_pdf_v2'),
    path('api/generate-recommendation/', generate_recommendation, name='generate-recommendation'),
    path('api/sync-user-project/', sync_user_project_view, name='sync-user-project'),
    path('api/get-location/', get_location_view, name='get-location'),
    path('api/get-ip-location/', get_ip_location_view, name='get-ip-location'),
    path("api/get-presigned-url/", get_presigned_url,  name='get-presigned-url'),
    path("api/image-converter/", convert_image, name='image-converter'),
    path('api/questions/save/', save_ptm_chats, name="save_ptm_chats"),
    path("api/track-view/<int:media_id>/", MediaViewTrackAPIView.as_view(), name="media-track-view"),
    path("api/track-download/<int:media_id>/", MediaDownloadTrackAPIView.as_view(), name="media-track-download"),
    path("api/track-solution-download/<str:project_id>/", SolutionDownloadTrackView.as_view(),
         name="project-solution-download-track"),

    path("api/search/", MediaSearchView.as_view(), name="media-search"),
    path("fetch-theme", FetchThemeView.as_view(), name="fetch-theme-no-slash"),
    path("fetch-theme/", FetchThemeView.as_view(), name="fetch-theme"),

    # path('admin/media/batch-upload/', BatchMediaUploadView.as_view(), name='batch_media_upload'),
    path('admin/media/batch-upload/', BatchMediaUploadView.as_view(), name='chatbot_media_batch_upload'),
    path('admin/media/google-drive-auth/', google_drive_integration.GoogleDriveAuthView.as_view(), name='admin_google_drive_auth'),
    path('admin/media/batch-extract/', BatchMediaExtractView.as_view(), name='chatbot_media_batch_extract'),
    path('admin/media/batch-save/', BatchMediaSaveView.as_view(), name='chatbot_media_batch_save'),
    path('admin/media/batch-task-status/', BatchMediaTaskStatusView.as_view(), name='chatbot_media_task_status'),


    # Retry endpoints
    path('admin/media/retry-extract/', BatchMediaRetryExtractView.as_view(), name='chatbot_media_retry_extract'),
    path('admin/media/retry-save/', BatchMediaRetrySaveView.as_view(), name='chatbot_media_retry_save'),

    path('admin/media/vector-db-task-status/', VectorDBTaskStatusView.as_view(), name='chatbot_media_vector_db_task_status'),

    # generic batch upload URLs
    path('admin/<str:app_label>/<str:model_name>/batch-upload/', GenericBatchUploadView.as_view(),
         name='generic_batch_upload'),
    path('admin/<str:app_label>/<str:model_name>/batch-template/', GenericBatchTemplateView.as_view(),
         name='generic_batch_template'),
    path('admin/<str:app_label>/<str:model_name>/batch-import/', GenericBatchImportView.as_view(),
         name='generic_batch_import'),


    # Media API endpoints
    path('api/v1/', include(router.urls)),
    path('api/v1/documents', DocumentUploadView.as_view(), name='document-upload'),
    path('google-drive/', google_drive_integration.GoogleDriveIntegrationView.as_view(), name='google_drive_integration'),
    path('google-drive/auth/', google_drive_integration.GoogleDriveAuthView.as_view(), name='google_drive_auth'),
    path('google-drive/callback/', google_drive_integration.GoogleDriveCallbackView.as_view(), name='google_drive_callback'),
    path('google-drive/files/import/', google_drive_integration.GoogleDriveFileImportView.as_view(), name='google_drive_file_import'),
    
    # Media Search V2 - Vector Database powered search
    path('api/v2/media/', MediaSearchV2View.as_view(), name='media-search-v2'),
    
    # AI Documents Search - Alternative endpoint for the same functionality
    path('ai/documents/search', MediaSearchV2View.as_view(), name='ai-documents-search'),

]
