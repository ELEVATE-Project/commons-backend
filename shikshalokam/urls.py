from django.urls import path

from shikshalokam.views.project_views import ProjectListCreateView, duplicate_project_view, project_ingestion_view
from shikshalokam.views.story_views import create_story_from_project_view
from shikshalokam.views.wishlist_views import wishlist_project_view
from shikshalokam.views.mitra_views import paraphrase_view, generate_objectives_view, validate_objectives_view, validate_actions_view, generate_action_list_view, generate_title_view, validate_title_view, update_project_status_view
from shikshalokam.views.profile_views import read_elevate_profile

app_name = "shikshalokam"

urlpatterns = [
    path('create-story/', create_story_from_project_view, name='create story'),
    path('project/', ProjectListCreateView.as_view(), name='project-list-create'),
    path('start-project/', duplicate_project_view, name='start-project'),
    path('ingest-data/', project_ingestion_view, name='ingest-data'),
    path('wishlist-project/', wishlist_project_view, name='wishlist-project'),
    path('paraphrase/', paraphrase_view, name='paraphrase'),
    path('generate-objective/', generate_objectives_view, name='generate-objectives'),
    path('validate-objective/', validate_objectives_view, name='validate-objectives'),
    path('validate-actions/', validate_actions_view, name='validate-actions'),
    path('generate-action-list/', generate_action_list_view, name='generate-action-list'),
    path('generate-title/', generate_title_view, name='generate-title'),
    path('validate-title/', validate_title_view, name='validate-title'),
    path('update-project-status/', update_project_status_view, name='update-project-status'),
    path('read-elevate-profile/', read_elevate_profile, name='read-elevate-profile'),

]
