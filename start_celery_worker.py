from celery import Celery
from shikshalokam_mohini.celery_config import app
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')

REDIS_HOST = os.environ.get('REDIS_HOST', "localhost")
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

app = Celery('shikshalokam_mohini', backend=f'redis://{REDIS_HOST}:{REDIS_PORT}', broker=f'redis://{REDIS_HOST}:{REDIS_PORT}')

# Load configuration from Django settings.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
if __name__ == '__main__':
    app.start(argv=['-A', 'shikshalokam_mohini.celery_config', 'worker', '--loglevel=info'])
