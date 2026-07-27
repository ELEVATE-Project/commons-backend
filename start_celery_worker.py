import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')

from shikshalokam_mohini.celery_config import app

if __name__ == '__main__':
    app.start(argv=['-A', 'shikshalokam_mohini.celery_config', 'worker', '--loglevel=info'])
