import re
import logging
from typing import List, Optional
from urllib.parse import urlparse
from chatbot.models import FileTypeChoices

logger = logging.getLogger('django')


def normalize_url_for_tracking(url: str) -> str:
    """
    Normalize URL for deduplication tracking
    """
    try:
        # Remove trailing slashes
        normalized = url.rstrip('/')

        # For Google Docs/Sheets, normalize parameters
        if 'docs.google.com' in normalized:
            # Extract the document/sheet ID
            if '/d/' in normalized:
                doc_id = normalized.split('/d/')[1].split('/')[0]

                if 'spreadsheets' in normalized:
                    # For spreadsheets, ignore gid parameter
                    base = f"https://docs.google.com/spreadsheets/d/{doc_id}"
                elif 'document' in normalized:
                    base = f"https://docs.google.com/document/d/{doc_id}"
                elif 'forms' in normalized:
                    base = f"https://docs.google.com/forms/d/{doc_id}"
                else:
                    base = normalized.split('?')[0].split('#')[0]

                return base

        # For other URLs, remove query parameters for normalization
        return normalized.split('?')[0].split('#')[0]

    except Exception as e:
        logger.error(f"Error normalizing URL {url}: {e}")
        return url


def determine_media_type_from_url(url: str) -> Optional[str]:
    """
    Determine media type from URL
    """
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()

        # Extract extension if present
        if '.' in path:
            extension = path.rsplit('.', 1)[-1]

            # Check if it's a valid extension first
            if not FileTypeChoices.is_valid_extension(extension):
                logger.warning(f"Invalid extension {extension} in URL {url}")
                return None  # Return None for invalid extensions

            # Use the existing method instead of hardcoding
            mime_type = FileTypeChoices.get_mime_from_extension(extension)
            if mime_type:
                return mime_type.value
            else:
                # Extension is valid but not mapped - default to TXT
                logger.warning(f"No MIME type mapping for valid extension {extension}")
                return FileTypeChoices.TXT.value

        # No extension found - default to TXT
        return FileTypeChoices.TXT.value

    except Exception as e:
        logger.error(f"Error determining media type from URL {url}: {e}")
        return FileTypeChoices.TXT.value


def convert_google_drive_url(url: str) -> str:
    """
    Convert Google URLs to downloadable formats - includes spreadsheets and forms
    """
    try:
        if 'docs.google.com/document' in url:
            if '/d/' in url:
                doc_id = url.split('/d/')[1].split('/')[0]
                return f"https://docs.google.com/document/d/{doc_id}/export?format=docx"

        elif 'drive.google.com/file' in url:
            if '/d/' in url:
                file_id = url.split('/d/')[1].split('/')[0]
                return f"https://drive.google.com/uc?id={file_id}&export=download"

        elif 'docs.google.com/spreadsheets' in url:
            if '/d/' in url:
                sheet_id = url.split('/d/')[1].split('/')[0]
                # Remove any gid parameter for export
                return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"

        elif 'docs.google.com/forms' in url:
            # Google Forms can't be downloaded as documents
            # Return the URL as-is, it will be handled as non-downloadable
            logger.info(f"Google Form detected, cannot convert to downloadable format: {url}")
            return url

        return url
    except Exception as e:
        logger.error(f"Error converting Google Drive URL: {e}")
        return url


def get_comprehensive_content_for_url_extraction(document_text: str, other_data: dict = None) -> str:
    """
    Get comprehensive content for URL extraction from the original file
    """
    try:
        # If we have the comprehensive content stored in other_data, use it
        if other_data and 'comprehensive_text_for_urls' in other_data:
            comprehensive_text = other_data['comprehensive_text_for_urls']
            logger.info(f"Using stored comprehensive content: {len(comprehensive_text)} chars")
            return comprehensive_text

        # Fallback to the document_text if no comprehensive content available
        logger.info(f"No comprehensive content available, using document text: {len(document_text)} chars")
        return document_text

    except Exception as e:
        logger.error(f"Error getting comprehensive content: {e}")
        return document_text


def find_explicit_tag_sections(document_text: str) -> List[str]:
    """
    Find explicit tag/classification sections in the document
    """
    try:
        tag_sections = []

        # Common patterns for explicit tag/classification sections
        tag_patterns = [
            r'(?:tags?|keywords?|categories|classification|subject areas?|topics?|themes?):\s*([^\n\r]+)',
            r'(?:^|\n)(?:tags?|keywords?|categories|classification|subject areas?|topics?|themes?):?\s*\n([^\n\r]+(?:\n[^\n\r]+)*?)(?=\n\n|\n[A-Z]|\n\s*$|$)',
            r'(?:^|\n)(?:tags?|keywords?|categories|classification|subject areas?|topics?|themes?):?\s*\n((?:\s*[-•*]\s*[^\n\r]+\n?)+)',
            r'(?:^|\n)(?:tags?|keywords?|categories|classification|subject areas?|topics?|themes?):?\s*\n((?:\s*\d+\.\s*[^\n\r]+\n?)+)',
        ]

        doc_lower = document_text.lower()

        for pattern in tag_patterns:
            matches = re.finditer(pattern, doc_lower, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                section_content = match.group(1).strip()
                if section_content and len(section_content) > 2:
                    tag_sections.append(section_content)

        # Remove duplicates while preserving order
        unique_sections = []
        seen_content = set()
        for section in tag_sections:
            section_key = section.lower().strip()
            if section_key not in seen_content:
                unique_sections.append(section)
                seen_content.add(section_key)

        return unique_sections

    except Exception as e:
        logger.error(f"Error finding explicit tag sections: {e}")
        return []