import logging

from celery import shared_task

logger = logging.getLogger('django')


@shared_task
def classify_media_themes(media_id):
    from chatbot.models import Media
    from chatbot.utils.knowledge_service.theme_classification_service import MediaThemeClassificationService

    media = Media.objects.select_related('company_bot__company').filter(id=media_id).first()
    if not media:
        logger.warning(f"[ThemeClassifier] media_id={media_id} not found; skipping")
        return None

    try:
        return MediaThemeClassificationService(media).run().as_dict()
    except Exception as e:
        logger.exception(f"[ThemeClassifier] media_id={media_id} classification failed: {e}")
        raise
