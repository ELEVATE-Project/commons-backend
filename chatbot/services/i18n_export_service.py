"""
Service for exporting I18n translations to JSON format.
Prepares translations data for cloud storage upload.
"""
import json
import logging
from io import BytesIO
from typing import Dict, Any, List, Tuple, Optional
from chatbot.models import I18nTag, I18nTranslation
from chatbot.services.storage import StorageFactory, UploadConfig, UploadResult

logger = logging.getLogger('django')


# Predefined list of supported languages
SUPPORTED_LANGUAGES: List[Tuple[str, str]] = [
    ('en', 'English'),
    ('hi', 'Hindi'),
    ('kn', 'Kannada'),
    ('te', 'Telugu'),
]


def get_supported_languages() -> List[Tuple[str, str]]:
    """
    Returns the list of supported languages for i18n export.
    
    Returns:
        List of tuples containing (language_code, language_name)
    """
    return SUPPORTED_LANGUAGES


def generate_i18n_json_for_language(language: str) -> Dict[str, Dict[str, Any]]:
    """
    Generate JSON structure for all i18n tags and translations for a given language.
    
    Args:
        language: Language code (e.g., 'en', 'hi', 'kn')
    
    Returns:
        Dictionary structured as:
        {
            "tag_name": {
                "variable_name": "translated_value",
                ...
            },
            ...
        }
    """
    result: Dict[str, Dict[str, Any]] = {}

    tags = I18nTag.objects.all().order_by('tag_name')
    
    for tag in tags:
        tag_translations = {}
        
        # Fetch all translations for this tag in the specified language
        translations = I18nTranslation.objects.filter(
            tag_id=tag,
            language=language.lower()
        ).order_by('variable_name')
        
        for translation in translations:
            tag_translations[translation.variable_name] = translation.value
        
        # Only add tag to result if it has translations for this language
        if tag_translations:
            result[tag.tag_name] = tag_translations
    
    return result


def get_export_filename(language: str) -> str:
    """
    Generate the filename for the export JSON file.
    Following the S3 naming convention: translations/{language}/translations.json
    
    Args:
        language: Language code (e.g., 'en', 'hi')
    
    Returns:
        Filename string (e.g., 'translations_en.json')
    """
    return f"translations_{language}.json"


def get_s3_path(language: str) -> str:
    """
    Generate the S3 path for the translations file.
    
    Args:
        language: Language code (e.g., 'en', 'hi')
    
    Returns:
        S3 path string (e.g., 'translations/en/translations.json')
    """
    return f"translations/{language}/translations.json"


def generate_i18n_json_string(language: str, indent: int = 2) -> str:
    """
    Generate JSON string for all i18n translations in a given language.
    
    Args:
        language: Language code (e.g., 'en', 'hi')
        indent: JSON indentation level (default: 2)
    
    Returns:
        JSON string representation of the translations
    """
    data = generate_i18n_json_for_language(language)
    return json.dumps(data, ensure_ascii=False, indent=indent)


def export_single_language_to_cloud(language: str) -> UploadResult:
    """
    Export translations for a single language to cloud storage.
    
    Args:
        language: Language code (e.g., 'en', 'hi')
    
    Returns:
        UploadResult with upload details including public URL
    
    Raises:
        Exception: If upload fails
    """
    try:
        # Generate JSON content for the language
        json_content = generate_i18n_json_string(language)
        
        # Convert string to bytes
        json_bytes = json_content.encode('utf-8')
        file_obj = BytesIO(json_bytes)
        
        # Get storage handler
        storage_handler = StorageFactory.get_storage_handler()
        
        # Create upload configuration
        upload_config = UploadConfig(
            file_name='translations.json',
            file_type='application/json',
            folder_structure=f'translations/{language}/',
            acl='public-read'
        )
        
        # Upload to cloud storage
        result = storage_handler.upload_file(file_obj, upload_config)
        
        if result.success:
            logger.info(f"Successfully exported {language} translations to: {result.public_url}")
        else:
            logger.error(f"Failed to export {language} translations: {result.error}")
        
        return result
        
    except Exception as e:
        error_msg = f"Error exporting {language} translations: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def export_all_languages_to_cloud() -> List[Dict[str, Any]]:
    """
    Export translations for all supported languages to cloud storage.
    Rolls back all uploads if any single upload fails.
    
    Returns:
        List of dictionaries containing language code and public URL for each successful export
    
    Raises:
        Exception: If any upload fails (triggers rollback)
    """
    uploaded_files = []
    
    try:
        storage_handler = StorageFactory.get_storage_handler()
        
        # Export all languages
        for language_code, language_name in get_supported_languages():
            logger.info(f"Exporting {language_name} ({language_code}) translations...")
            
            result = export_single_language_to_cloud(language_code)
            
            if not result.success:
                raise Exception(f"Failed to export {language_name}: {result.error}")
            
            uploaded_files.append({
                'language_code': language_code,
                'language_name': language_name,
                'object_key': result.object_key,
                'public_url': result.public_url
            })
            
            logger.info(f"Exported {language_name} to: {result.public_url}")
        
        return uploaded_files
        
    except Exception as e:
        # Rollback: delete all uploaded files
        logger.error(f"Export failed, rolling back all uploads: {str(e)}")
        
        for uploaded in uploaded_files:
            try:
                storage_handler.delete_file(uploaded['object_key'])
                logger.info(f"Rolled back {uploaded['language_name']} export")
            except Exception as delete_error:
                logger.error(f"Failed to rollback {uploaded['language_name']}: {str(delete_error)}")
        
        raise Exception(f"Export failed and rolled back: {str(e)}")


def export_translations_to_cloud(language: Optional[str] = None) -> Dict[str, Any]:
    """
    Export i18n translations to cloud storage.
    
    Args:
        language: Language code to export, or 'all' to export all languages, or None for all
    
    Returns:
        Dictionary with export results:
        {
            'success': bool,
            'exports': List of exported files with URLs,
            'error': Optional error message
        }
    """
    try:
        if language == 'all' or language is None:
            # Export all languages
            exports = export_all_languages_to_cloud()
            return {
                'success': True,
                'exports': exports,
                'message': f'Successfully exported {len(exports)} languages'
            }
        else:
            # Export single language
            result = export_single_language_to_cloud(language)
            
            if not result.success:
                return {
                    'success': False,
                    'error': result.error
                }
            
            language_name = dict(get_supported_languages()).get(language, language)
            return {
                'success': True,
                'exports': [{
                    'language_code': language,
                    'language_name': language_name,
                    'object_key': result.object_key,
                    'public_url': result.public_url
                }],
                'message': f'Successfully exported {language_name}'
            }
            
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
