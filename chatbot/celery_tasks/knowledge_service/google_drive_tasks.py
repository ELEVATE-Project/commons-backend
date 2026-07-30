import os
import tempfile
import time
import uuid

from celery import shared_task
from django.core.cache import cache

from chatbot.celery_tasks.knowledge_service.tag_tasks import get_auto_extracted_data
from chatbot.models import CompanyBot, FileTypeChoices, Profile
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.knowledge_service.cache_manager import CacheManager
from chatbot.views.Media.save_views import BatchMediaSaveView
import chatbot.constants.constants as CONSTANTS
import chatbot.constants.dialogue_messages as MESSAGES

def _get_status_cache_key(session_id):
    return CacheManager.get_cache_key(session_id, 'google_drive_import', 'status')


def _set_import_status(session_id, payload):
    cache.set(_get_status_cache_key(session_id), payload, timeout=7200)


def _merge_extraction_result(item, ai_result):
    if not isinstance(ai_result, dict):
        return item

    enhanced = ai_result.get('enhanced_data')
    if not isinstance(enhanced, dict):
        enhanced = {}

    # Support both response shapes:
    # - current AI extractor output with top-level summary/title/description
    # - older or nested output under enhanced_data
    source = ai_result

    # Extract tags from multiple possible field names
    raw_tags = source.get('tags') or source.get('auto_tags') or enhanced.get('tags') or enhanced.get('auto_tags') or []
    item['auto_tags'] = [
        tag.get('text') if isinstance(tag, dict) else tag
        for tag in raw_tags
    ]

    title = source.get('title') or enhanced.get('title')
    summary = source.get('summary') or enhanced.get('summary')
    description = source.get('description') or enhanced.get('description')

    if title:
        item['title'] = title
    if summary:
        item['summary'] = summary
    if description:
        item['description'] = description
    if 'extracted_text' in source or 'extracted_text' in enhanced:
        item['extracted_text'] = source.get('extracted_text') or enhanced.get('extracted_text') or ''
    if source.get('media_type') or enhanced.get('media_type'):
        item['media_type'] = source.get('media_type') or enhanced.get('media_type')

    key_values = source.get('key_values') or enhanced.get('enhanced_key_values')
    if isinstance(key_values, list):
        item['key_values'] = key_values
    if isinstance(source.get('subdocument'), list) or isinstance(enhanced.get('subdocument'), list):
        item['subdocument'] = source.get('subdocument') if isinstance(source.get('subdocument'), list) else enhanced.get('subdocument')
    if isinstance(source.get('failed_links'), list) or isinstance(enhanced.get('failed_links'), list):
        item['failed_links'] = source.get('failed_links') if isinstance(source.get('failed_links'), list) else enhanced.get('failed_links')
    if isinstance(source.get('images'), list) or isinstance(enhanced.get('images'), list):
        item['images'] = source.get('images') if isinstance(source.get('images'), list) else enhanced.get('images')
    if isinstance(source.get('url'), list) or isinstance(enhanced.get('url'), list):
        item['url'] = source.get('url') if isinstance(source.get('url'), list) else enhanced.get('url')
    if isinstance(source.get('source_documents'), list) or isinstance(enhanced.get('source_documents'), list):
        item['source_documents'] = source.get('source_documents') if isinstance(source.get('source_documents'), list) else enhanced.get('source_documents')

    return item


def _format_item_for_save(item, organization_slug):
    filename = item.get('filename') or ''
    filename_base = os.path.splitext(filename)[0] if filename else ''
    display_name = filename_base or item.get('name') or item.get('title')
    ai_title = str(item.get('title')).strip() if (item.get('title') and str(item.get('title')).strip()) else display_name
    fallback_description = f"Extracted from {item['filename']}" if item.get('filename') else ''
    summary = item.get('summary')
    description = item.get('description')
    final_description = summary.strip() if isinstance(summary, str) and summary.strip() else (
        description.strip() if isinstance(description, str) and description.strip() else fallback_description
    )

    return {
        'filename': item.get('filename'),
        'file_index': item.get('file_index'),
        'file_key': item.get('file_key'),
        'name': ai_title,
        'title': ai_title,
        'summary': final_description,
        'description': final_description,
        'media_type': item.get('media_type'),
        'priority': item.get('priority') or 'P1',
        'organization_slug': organization_slug,
        'organization_id': item.get('organization_id'),
        'extracted_text': item.get('extracted_text') or item.get('exact_content') or '',
        'key_values': item.get('key_values') or [],
        'auto_tags': item.get('auto_tags') or [],
        'manual_tags': item.get('manual_tags') or [],
        'subdocument': item.get('subdocument') or [],
        'source_documents': item.get('source_documents') or [],
        'images': item.get('images') or [],
        'source_url': item.get('source_url'),
        'source_provider': item.get('source_provider'),
        'source_folder_url': item.get('source_folder_url'),
        'source_file_id': item.get('source_file_id'),
    }


@shared_task
def process_google_drive_import(
    *,
    session_id,
    credentials_data,
    folder_url,
    folder_id,
    company_id=None,
    company_bot_id=None,
    profile_id=None,
    repository_id=None,
):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    from chatbot.models import Company
    from chatbot.models.repository_models import Repository
    from chatbot.views.Media.google_drive_integration import (
        download_drive_file,
        get_all_files_in_folder,
        get_default_extraction_bot,
        resolve_company_from_import,
        upsert_repository_from_drive_import,
    )

    _set_import_status(session_id, {
        'status': 'STARTED',
        'message': 'Google Drive import queued.',
        'session_id': session_id,
    })

    try:
        credentials = Credentials(**credentials_data)
        service = build('drive', 'v3', credentials=credentials)
    except Exception as exc:
        message = f'Failed to initialize Google Drive client: {exc}'
        _set_import_status(session_id, {
            'status': CONSTANTS.FAILED,
            'message': message,
            'session_id': session_id,
        })
        return {
            'session_id': session_id,
            'repository_id': repository_id,
            'successful': 0,
            'failed': 0,
            'error': message,
        }
    company = resolve_company_from_import(company_id)
    company_bot = CompanyBot.objects.filter(id=company_bot_id).first() if company_bot_id else None
    if not company_bot and company:
        company_bot = CompanyBot.objects.filter(company=company, route='/tag_extractor').first()
    company_bot = company_bot or get_default_extraction_bot()
    user_profile = Profile.objects.filter(id=profile_id).first() if profile_id else None

    if not company_bot:
        _set_import_status(session_id, {
            'status': CONSTANTS.FAILED,
            'message': 'No company bot available for Google Drive import.',
            'session_id': session_id,
        })
        if repository_id:
            upsert_repository_from_drive_import(
                folder_url=folder_url,
                folder_meta={'id': folder_id},
                company=company,
                repository_id=repository_id,
                status=CONSTANTS.FAILED,
                total_resources=0,
                error_message='No company bot available for Google Drive import.',
                created_by=user_profile,
                updated_by=user_profile,
            )
        return

    try:
        folder_meta = service.files().get(
            fileId=folder_id,
            fields="id, name, mimeType, permissions"
        ).execute()
        is_public = any(p.get('type') == 'anyone' for p in folder_meta.get('permissions', []))
        if not is_public:
            _set_import_status(session_id, {
                'status': CONSTANTS.FAILED,
                'message': MESSAGES.NOT_PUBLIC_DRIVE_FOLDER_MESSAGE,
                'session_id': session_id,
            })
            # A non-public folder must not leave a repository row behind; remove
            # the IN-PROGRESS row created when the import was queued.
            if repository_id:
                Repository.objects.filter(id=repository_id).delete()
            return
    except HttpError as exc:
        _set_import_status(session_id, {
            'status': CONSTANTS.FAILED,
            'message': f'Failed to read Google Drive folder: {exc}',
            'session_id': session_id,
        })
        if repository_id:
            upsert_repository_from_drive_import(
                folder_url=folder_url,
                folder_meta={'id': folder_id},
                company=company,
                repository_id=repository_id,
                status=CONSTANTS.FAILED,
                total_resources=0,
                error_message=f'Failed to read Google Drive folder: {exc}',
                created_by=user_profile,
                updated_by=user_profile,
            )
        return

    all_files = get_all_files_in_folder(service, folder_id)
    if not all_files:
        _set_import_status(session_id, {
            'status': CONSTANTS.FAILED,
            'message': MESSAGES.EMPTY_DRIVE_FOLDER_MESSAGE,
            'session_id': session_id,
        })
        # An empty folder must not leave a repository row behind; remove the
        # IN-PROGRESS row created when the import was queued.
        if repository_id:
            Repository.objects.filter(id=repository_id).delete()
        return

    save_view = BatchMediaSaveView()
    save_view._source_doc_cache = {}
    processed_results = []

    for i, file_info in enumerate(all_files):
        file_id = file_info['id']
        original_name = file_info['name']
        file_url = f"{CONSTANTS.HTTPS_PROTOCOL}{CONSTANTS.GOOGLE_DRIVE_HOSTNAME}/file/d/{file_id}/view?usp=sharing"

        # Skip clearly unsupported files before downloading them. Extensionless
        # files (e.g. native Google Docs) pass here and are re-checked after the
        # export MIME type is known below.
        if '.' in original_name:
            prelim_ext = original_name.rsplit('.', 1)[-1].lower()
            if not FileTypeChoices.is_valid_extension(prelim_ext):
                print(
                    f"[DriveImport] Ignoring unsupported file '{original_name}' "
                    f"(extension: '{prelim_ext}')"
                )
                continue

        try:
            metadata, content = download_drive_file(service, file_id)
            file_url = metadata.get('webViewLink') or file_url
            original_mime_type = metadata.get('mimeType', '')
            exported_mime_type = {
                'application/vnd.google-apps.document': 'application/pdf',
                'application/vnd.google-apps.spreadsheet': 'text/csv',
                'application/vnd.google-apps.presentation': 'application/pdf',
            }.get(original_mime_type, original_mime_type)
            if '.' in original_name:
                extension = original_name.rsplit('.', 1)[-1].lower()
            else:
                # No extension (e.g. native Google Docs/Sheets/Slides that were
                # exported). Derive the extension from the exported MIME type.
                mime_to_ext = {
                    str(mime): ext.lstrip('.')
                    for mime, ext in FileTypeChoices.get_extension_mapping().items()
                }
                extension = mime_to_ext.get(exported_mime_type, '')

            # Only allow the supported document types. Any other file is ignored
            # entirely — do not process, cache, or persist it.
            if not FileTypeChoices.is_valid_extension(extension):
                print(
                    f"[DriveImport] Ignoring unsupported file '{original_name}' "
                    f"(extension: '{extension or 'none'}')"
                )
                continue

            # Ensure the filename carries the resolved extension.
            if '.' not in original_name:
                original_name = f"{original_name}.{extension}"

            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            class DummyFile:
                def __init__(self, name, size, content):
                    self.name = name
                    self.size = size
                    self._content = content

                def chunks(self):
                    chunk_size = 8192
                    for idx in range(0, len(self._content), chunk_size):
                        yield self._content[idx:idx + chunk_size]

            file_index = int(time.time() * 1000000) + i
            file_key = CacheManager.cache_file(
                DummyFile(original_name, len(content), content),
                session_id,
                file_index,
            )

            master_tags = TagProcessor.get_master_tags(
                company=company,
                other_params=company_bot.other_params if company_bot else None,
            )
            other_data = {
                'master_tag': master_tags,
                'original_filename': original_name,
            }

            actual_media_type = FileTypeChoices.get_mime_from_extension(extension) or FileTypeChoices.TXT.value
            base_name = original_name.rsplit('.', 1)[0] if '.' in original_name else original_name
            item = {
                'filename': original_name,
                'file_index': file_index,
                'name': base_name,
                'media_type': actual_media_type,
                'description': f'Extracted from {original_name}',
                'priority': 'P1',
                'tags': [],
                'manual_tags': [],
                'auto_tags': [],
                'key_values': [],
                'subdocument': [],
                'images': [],
                'failed_links': [],
                'organization': company.name if company else '',
                'organization_slug': company.slug if company else '',
                'organization_id': company.id if company else None,
                'source_url': file_url,
                'source_provider': CONSTANTS.GOOGLE_DRIVE,
                'source_folder_url': folder_url,
                'source_file_id': file_id,
                'file_key': file_key,
                'status': 'success',
                'session_id': session_id,
            }

            ai_result = get_auto_extracted_data(
                file_path=tmp_path,
                company_bot_id=company_bot.id,
                file_extension=extension,
                other_data=other_data,
            )
            item = _merge_extraction_result(item, ai_result)

            result = save_view.save_single_item_with_vector_db_wait_safe(
                item_data=_format_item_for_save(item, company.slug if company else ''),
                company_bot_id=company_bot.id,
                user_profile=user_profile,
                session_id=session_id,
                bypass_similarity=False,
            )
            processed_results.append(result)
        except Exception as exc:
            processed_results.append({
                'success': False,
                'filename': original_name,
                'message': str(exc),
                'file_index': i,
                'session_id': session_id,
            })

    success_count = sum(1 for result in processed_results if result.get('success'))
    failed_count = len(processed_results) - success_count
    final_status = CONSTANTS.COMPLETED if success_count else CONSTANTS.FAILED

    repository = upsert_repository_from_drive_import(
        folder_url=folder_url,
        folder_meta=folder_meta,
        company=company,
        repository_id=repository_id,
        status=final_status,
        total_resources=len(all_files),
        error_message='All files failed to import.' if not success_count else None,
        created_by=user_profile,
        updated_by=user_profile,
    )

    _set_import_status(session_id, {
        'status': final_status,
        'message': f'Google Drive import finished. {success_count} succeeded, {failed_count} failed.',
        'session_id': session_id,
        'repository_id': str(repository.id) if repository else None,
        'results': processed_results,
    })

    return {
        'session_id': session_id,
        'repository_id': str(repository.id) if repository else None,
        'successful': success_count,
        'failed': failed_count,
    }
