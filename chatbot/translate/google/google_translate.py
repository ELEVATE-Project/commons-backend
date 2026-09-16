import traceback
import threading
from google.cloud import translate
import logging
from google.oauth2 import service_account
from django.conf import settings

logger = logging.getLogger('django')

_client_lock = threading.Lock()
_translation_client = None


def _get_client():
    global _translation_client
    if _translation_client is None:
        with _client_lock:
            if _translation_client is None:
                credentials = service_account.Credentials.from_service_account_file(settings.SECRETS_JSON_PATH)
                _translation_client = translate.TranslationServiceClient(credentials=credentials)
    return _translation_client


def translate_text(
    text: str,
    project_id: str,
    source_language_code: str,
    target_language_code: str,
    voice_provider: any,
):
    """Translating Text."""
    try:

        other_params = voice_provider.other_params if voice_provider.other_params else {}

        client = _get_client()

        location = other_params.get("location", "global")
        parent = f"projects/{project_id}/locations/{location}"
        glossary_id = other_params.get("glossary_id")

        request = {
            "parent": parent,
            "contents": [text],
            "mime_type": "text/plain",
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
        }

        if glossary_id:
            glossary = client.glossary_path(project_id, location, glossary_id)
            glossary_config = translate.TranslateTextGlossaryConfig(glossary=glossary)
            request["glossary_config"] = glossary_config

        response = client.translate_text(request=request)
        logger.info(f"Response from Google Text Translate: {response}")
        translations = response.glossary_translations if glossary_id else response.translations

        for translation in translations:
            return {
                'status': 200,
                'content': translation.translated_text
            }

    except Exception as e:
        logger.error(f'Error processing Google Text Translate:{e}')
        print(f"Error during translation API call: {str(e)}")
        traceback.print_exc()
        return {
            'status': 500,
            'content': f"Error during translation API call: {str(e)}"
        }
