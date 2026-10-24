import logging
import os
import time

from celery import current_task, shared_task

from chatbot.utils.knowledge_service.base.main import get_doc_tags_from_ai

logger = logging.getLogger('django')


def _log_prefix(other_data):
    task_id = getattr(getattr(current_task, 'request', None), 'id', None) or 'sync'
    file_name = (other_data or {}).get('original_filename') or '-'
    return f"[DocExtractor] task_id={task_id} file={file_name}"


def _describe_extraction(result):
    document_type = result.get('document_type')
    if isinstance(document_type, dict):
        document_type = document_type.get('type')
    tags = [tag.get('text') if isinstance(tag, dict) else tag for tag in result.get('tags') or []]
    return (
        f"title={result.get('title')!r} document_type={document_type!r} "
        f"summary_chars={len(result.get('summary') or '')} tags={tags} "
        f"key_entities={len(result.get('key_entities') or [])} subdocuments={len(result.get('subdocument') or [])} "
        f"media_type={result.get('media_type')!r}"
    )


@shared_task
def get_auto_extracted_data(file_path, company_bot_id=None, file_extension=None, other_data=None):
    from chatbot.models import CompanyBot

    log_prefix = _log_prefix(other_data)
    started_at = time.monotonic()
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
    logger.info(
        f"{log_prefix} extraction started extension={file_extension} size_bytes={file_size} "
        f"company_bot_id={company_bot_id}"
    )

    company_bot = None
    if company_bot_id:
        try:
            company_bot = CompanyBot.objects.get(id=company_bot_id)
        except CompanyBot.DoesNotExist:
            logger.warning(f"{log_prefix} company_bot_id={company_bot_id} not found; extracting without a bot")

    extracted_data = None
    try:
        extracted_data = get_doc_tags_from_ai(
            file=file_path,
            company_bot=company_bot,
            file_extension=file_extension,
            other_data=other_data
        )
        if extracted_data and other_data and other_data.get('original_filename'):
            extracted_data['original_filename'] = other_data['original_filename']

        duration = time.monotonic() - started_at
        if not extracted_data:
            logger.warning(f"{log_prefix} extraction returned no data duration={duration:.1f}s")
        elif extracted_data.get('error'):
            logger.error(
                f"{log_prefix} extraction failed duration={duration:.1f}s "
                f"error_type={extracted_data.get('error_type')} error={extracted_data.get('error')}"
            )
        else:
            logger.info(
                f"{log_prefix} extraction completed duration={duration:.1f}s {_describe_extraction(extracted_data)}"
            )

    except Exception as e:
        logger.exception(f"{log_prefix} extraction crashed duration={time.monotonic() - started_at:.1f}s: {e}")
    finally:
        # cleanup file no matter what
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as cleanup_err:
                logger.warning(f"{log_prefix} failed to remove temp file {file_path}: {cleanup_err}")

    return extracted_data
