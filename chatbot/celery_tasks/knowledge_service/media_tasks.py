from celery import shared_task
import os
from chatbot.models import LLMProvider
from chatbot.utils.database_util import update_single_file, delete_single_file, upsert_single_file
import logging

from chatbot.utils.knowledge_service.openai_vector_store.vector_store_utils import upload_file_to_openai, \
    add_file_to_vector_store, delete_file_from_vector_store

logger = logging.getLogger('django')
S3_BASE_URL = os.getenv('S3_MEDIA_URL')


def prepare_vector_db_data(media_id, company_slug=None):
    """Helper method to prepare data for vector DB operations"""
    from chatbot.models import KeyValue, Media, Company
    media = Media.objects.get(id=media_id)
    kvs = KeyValue.objects.filter(media=media)
    company_obj = None
    if company_slug:
        company_obj = Company.objects.filter(slug=company_slug).first()
    company_obj = company_obj or media.organization

    metadata = {
        'source': 'file',
        'url': str(media.url) if media.url is not None else S3_BASE_URL + media.file.name,
        'markdown_url':  "" if not media.markdown_file else S3_BASE_URL + media.markdown_file.name,
        'company': company_obj.slug,
        'created_at': str(media.created_at),
        'type': media.media_type,
        'priority': media.priority,
        'updated_at': str(media.updated_at)
    }

    # Add file_size if file exists
    if media.file:
        try:
            metadata['file_size'] = media.file.size
        except (ValueError, AttributeError):
            metadata['file_size'] = None

    # Add organization_url if organization exists
    if company_obj and company_obj.url:
        metadata['organization_url'] = company_obj.url

    for kv in kvs:
        metadata[kv.key] = kv.value
    metadata['tags'] = list(media.tags.values_list('name', flat=True))

    with media.file.open("rb") as file:
        file_content = file.read()
    file_name = media.file.name.split("/")[-1]

    return media, file_name, file_content, metadata


@shared_task
def save_in_vector_db(media_id, company_slug=None):
    print(f"Save in vector for media_id: {media_id}, company_slug: {company_slug}")
    media, file_name, file_content, metadata = prepare_vector_db_data(
        media_id=media_id,
        company_slug=company_slug
    )
    if media and media.company_bot and media.company_bot.provider == LLMProvider.OPENAI:
        status_code, upload_response = upload_file_to_openai(
            file_name=file_name, file_content=file_content
        )
        if status_code != 200 or not upload_response:
            return 500

        file_id = upload_response.get("id")
        if not file_id:
            logger.error("OpenAI upload succeeded but file_id missing")
            return 500

        from chatbot.models.media_models import Media
        Media.objects.filter(id=media.id).update(
            external_file_id=file_id
        )
        media.refresh_from_db()

        status_code, vector_response = add_file_to_vector_store(
            media=media, metadata=metadata
        )

        return status_code
    else:
        status_code, response_text = upsert_single_file(file_name, file_content, metadata, media)
        print(status_code, response_text)
        return status_code


@shared_task
def update_in_vector_db(media_id, company_slug=None):
    print('Update in vector for media_id: {}'.format(media_id))
    media, file_name, file_content, metadata = prepare_vector_db_data(
        media_id=media_id,
        company_slug=company_slug
    )
    status_code, response_text = update_single_file(media_id, file_name, file_content, metadata, media)
    print("Updated in vector DB:", status_code, response_text)
    return status_code

@shared_task
def delete_from_vector_db(media_id):
    print('Deleting from vector for media_id: {}'.format(media_id))
    from chatbot.models import Media

    try:
        media = Media.objects.get(id=media_id)
    except Media.DoesNotExist:
        return 404

    if media.company_bot and media.company_bot.provider == LLMProvider.OPENAI:
        status_code, response = delete_file_from_vector_store(
            media=media
        )

        return status_code
    else:
        company_slug = media.organization.slug if media and media.organization else None
        status_code, response_text = delete_single_file(media_id, company_slug)
        print(status_code, response_text)
        return status_code


@shared_task(bind=True, max_retries=3)
def generate_media_preview(self, media_id):
    """
    Generate preview/thumbnail for uploaded media
    """
    import tempfile
    from chatbot.models import Media

    try:
        from chatbot.utils.media_preview import ThumbnailGenerator
        from django.core.files.base import ContentFile
        from io import BytesIO

        media = Media.objects.get(id=media_id)

        if not media.file:
            logger.info(f"No file found for media_id {media_id}")
            return None

        temp_file = None

        try:
            file_path = media.file.path
        except (NotImplementedError, AttributeError):
            logger.info(f"File is on S3, downloading for media_id {media_id}")
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(media.file.name)[1])
            media.file.open('rb')
            temp_file.write(media.file.read())
            media.file.close()
            temp_file.close()
            file_path = temp_file.name

        thumbnail = ThumbnailGenerator.generate_thumbnail(file_path)

        if thumbnail:
            buffer = BytesIO()
            thumbnail.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)

            filename = f"thumb_{media.id}.jpg"
            media.thumbnail.save(filename, ContentFile(buffer.getvalue()), save=False)

            Media.objects.filter(pk=media.id).update(thumbnail=media.thumbnail)

            logger.info(f"Successfully generated preview for media_id {media_id}")
            return f"Preview generated for {media.name}"
        else:
            logger.info(f"Could not generate preview for media_id {media_id}")
            return None

    except Media.DoesNotExist:
        logger.error(f"Media with id {media_id} does not exist")
        return None
    except Exception as e:
        logger.error(f"Error generating preview for media_id {media_id}: {str(e)}")
        raise self.retry(exc=e, countdown=60)
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.info(f"Could not delete temp file: {str(e)}")
