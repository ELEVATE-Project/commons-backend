import logging
from typing import Dict, Any

# Set up logging
logger = logging.getLogger('django')

# Default configuration constants
MAX_DEPTH = 1
DEFAULT_MAX_SUBDOCS = 10
DEFAULT_MAIN_DOC_MAX_CHARS = 3000
DEFAULT_SUBDOC_MAX_CHARS = 500
DEFAULT_EXCEL_MAX_ROWS = 50
DEFAULT_EXCEL_MAX_COLS = 20
DEFAULT_MAX_FILE_SIZE_MB = 50

# URL patterns for document extraction
GOOGLE_DOC_PATTERNS = [
    'docs.google.com/document',
    'drive.google.com/file',
    'docs.google.com/spreadsheets',
    'docs.google.com/forms',
    'docs.google.com/presentation'
]

# Excluded domains for URL extraction
EXCLUDED_DOMAINS = [
    'googleusercontent.com',
    'gstatic.com',
    'chrome.google.com',
    'googleapis.com',
    'youtube.com',
    'twitter.com',
    'forms.google.com'
]

# HTTP headers for document downloads
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# Google Drive access denial patterns
ACCESS_DENIED_PATTERNS = [
    'You need access',
    'Request access',
    'Access denied',
    'Permission denied',
    'Sign in to continue',
    'This file is private',
    'Sorry, unable to open',
    'Google Accounts',
    'docs.google.com/forms'
]


def parse_extractor_config(company_bot) -> Dict[str, Any]:
    """Parse DocumentExtractor configuration from company_bot's other_params

    Args:
        company_bot: Company bot instance with configuration

    Returns:
        Dictionary with extractor configuration
    """
    extractor_config = {
        'max_depth': MAX_DEPTH,
        'max_subdocs': DEFAULT_MAX_SUBDOCS,
        'enable_ocr': True,
        'compress_images': True,
        'extract_images': False,
        'main_doc_max_chars': DEFAULT_MAIN_DOC_MAX_CHARS,
        'subdoc_max_chars': DEFAULT_SUBDOC_MAX_CHARS,
        'excel_max_rows': DEFAULT_EXCEL_MAX_ROWS,
        'excel_max_cols': DEFAULT_EXCEL_MAX_COLS,
        'max_file_size_mb': DEFAULT_MAX_FILE_SIZE_MB,
    }

    if company_bot and hasattr(company_bot, 'other_params') and company_bot.other_params:
        try:
            import json
            import json_repair

            other_params = json_repair.repair_json(company_bot.other_params, return_objects=True) if isinstance(
                company_bot.other_params, str) else company_bot.other_params

            # Extract DocumentExtractor configuration
            if other_params:
                extractor_config.update({
                    'max_depth': other_params.get('max_depth', MAX_DEPTH),
                    'max_subdocs': other_params.get('max_subdocs', DEFAULT_MAX_SUBDOCS),
                    'enable_ocr': other_params.get('enable_ocr', True),
                    'compress_images': other_params.get('compress_images', True),
                    'extract_images': other_params.get('extract_images', False),
                    'main_doc_max_chars': other_params.get('main_doc_max_chars', DEFAULT_MAIN_DOC_MAX_CHARS),
                    'subdoc_max_chars': other_params.get('subdoc_max_chars', DEFAULT_SUBDOC_MAX_CHARS),
                    'excel_max_rows': other_params.get('excel_max_rows', DEFAULT_EXCEL_MAX_ROWS),
                    'excel_max_cols': other_params.get('excel_max_cols', DEFAULT_EXCEL_MAX_COLS),
                    'max_file_size_mb': other_params.get('max_file_size_mb', DEFAULT_MAX_FILE_SIZE_MB),
                })
        except Exception as e:
            logger.error(f"Error parsing other_params: {e}")

    return extractor_config