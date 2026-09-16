from celery import shared_task
import os
from chatbot.utils.knowledge_service.base.main import get_doc_tags_from_ai


@shared_task
def get_auto_extracted_data(file_path, company_bot_id=None, file_extension=None, other_data=None):
    from chatbot.models import CompanyBot

    company_bot = None
    if company_bot_id:
        try:
            company_bot = CompanyBot.objects.get(id=company_bot_id)
        except CompanyBot.DoesNotExist:
            pass

    extracted_data=None
    try:
        extracted_data = get_doc_tags_from_ai(
            file=file_path,
            company_bot=company_bot,
            file_extension=file_extension,
            other_data=other_data
        )
        if extracted_data and other_data and other_data.get('original_filename'):
            extracted_data['original_filename'] = other_data['original_filename']

    except Exception as e:
        # log the error if needed
        print(f"[AutoTags] Error processing {file_path}: {e}")
    finally:
        # cleanup file no matter what
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as cleanup_err:
                print(f"[AutoTags] Failed to remove temp file {file_path}: {cleanup_err}")

    return extracted_data