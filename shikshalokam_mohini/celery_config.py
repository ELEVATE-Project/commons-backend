import os
from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')

REDIS_HOST = os.environ.get('REDIS_HOST', "localhost")
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

app = Celery('shikshalokam_mohini', backend=f'redis://{REDIS_HOST}:{REDIS_PORT}', broker=f'redis://{REDIS_HOST}:{REDIS_PORT}')
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks([
    'chatbot.celery_tasks.shikshalokam_bedrock_tasks',
    'chatbot.celery_tasks.one_shot_bedrock_tasks',
    'chatbot.celery_tasks.chaupal_tasks',
    'chatbot.celery_tasks.common_chat_tasks',
    'chatbot.celery_tasks.reflection_bedrock_tasks',
    'chatbot.celery_tasks.mitra_bedrock_tasks',
    'chatbot.utils.story_utils',
    'chatbot.celery_tasks.guided_guest_tasks',
    'chatbot.celery_tasks.oneshot_guest_tasks',
    'chatbot.celery_tasks.ptm_report_tasks',
    'chatbot.celery_tasks.knowledge_service.tag_tasks',
    'chatbot.celery_tasks.knowledge_service.media_tasks',
    'chatbot.celery_tasks.flow_tasks',
    'chatbot.celery_tasks.free_flow_tasks',
    'chatbot.celery_tasks.post_processing_tasks'
])
