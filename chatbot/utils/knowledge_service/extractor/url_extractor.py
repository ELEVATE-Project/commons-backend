"""URL extraction and processing functionality"""

import re
import logging
from typing import List, Set
from urllib.parse import urlparse
from chatbot.utils.knowledge_service.base.extraction_config import EXCLUDED_DOMAINS, GOOGLE_DOC_PATTERNS
from chatbot.models import FileTypeChoices

logger = logging.getLogger('django')


class URLExtractor:
    """Handles URL extraction and validation for documents"""

    def __init__(self):
        self.processed_urls: Set[str] = set()

    def extract_urls_from_text(self, text: str) -> List[str]:
        """
        Extract all URLs from text content with improved regex
        """
        try:
            # Log the full text for debugging
            logger.info("=" * 80)
            logger.info("EXTRACTING URLs FROM TEXT")
            logger.info("=" * 80)

            # First, let's look specifically for patterns like "word: URL" on separate lines
            lines = text.split('\n')
            manual_urls = []

            for i, line in enumerate(lines):
                line = line.strip()

                # Check if line contains http anywhere
                if 'http' in line:
                    # Extract all URLs from this line
                    url_pattern = r'https?://[^\s\n\r]+'
                    found_urls = re.findall(url_pattern, line, re.IGNORECASE)
                    manual_urls.extend(found_urls)

                # Also check if previous line ends with description and this line is a URL
                if i > 0 and line.startswith('http'):
                    if line not in manual_urls:
                        manual_urls.append(line)

            # Enhanced URL patterns for more thorough extraction
            url_patterns = [
                # Catch ALL URLs starting with http/https
                r'https?://[^\s\n\r]+',
                # Google specific patterns
                r'https://docs\.google\.com/[^/\s]+/d/[A-Za-z0-9_-]+[^\s\n\r]*',
                r'https://drive\.google\.com/[^/\s]+/d/[A-Za-z0-9_-]+[^\s\n\r]*',
            ]

            urls = []

            # Add manually found URLs first
            urls.extend(manual_urls)

            # Then use regex patterns on the full text
            for pattern in url_patterns:
                found_urls = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
                urls.extend(found_urls)

            # Clean and process URLs
            processed_urls = []
            for url in urls:
                url = url.strip()
                # Remove trailing punctuation and special chars
                url = re.sub(r'[.,;:!?)\]}>]+$', '', url)
                if url.startswith('www.'):
                    url = 'https://' + url
                processed_urls.append(url)

            # Remove duplicates while preserving order
            unique_urls = []
            seen = set()

            for url in processed_urls:
                # Normalize by removing trailing slashes
                normalized = url.rstrip('/')

                # For Google Docs/Sheets, normalize the gid parameter
                if 'docs.google.com/spreadsheets' in normalized and '#gid=' in normalized:
                    base_url = normalized.split('#gid=')[0]
                    gid_part = '#gid=' + normalized.split('#gid=')[1].split('&')[0].split('/')[0]
                    normalized = base_url + gid_part

                if normalized not in seen and len(normalized) > 10:
                    unique_urls.append(url)
                    seen.add(normalized)

            logger.info("=" * 80)
            logger.info(f"EXTRACTED {len(unique_urls)} UNIQUE URLs:")
            logger.info("=" * 80)
            for i, url in enumerate(unique_urls):
                logger.info(f"URL {i + 1}: {url}")
            logger.info("=" * 80)

            return unique_urls

        except Exception as e:
            logger.error(f"Error extracting URLs: {e}")
            return []

    def is_document_url(self, url: str, depth: int = 0) -> bool:
        """
        Check if URL points to a document - validates against supported formats
        """
        try:
            # Check domain exclusions
            for domain in EXCLUDED_DOMAINS:
                if domain in url.lower():
                    return False

            # Special handling for Google Docs
            if any(pattern in url for pattern in GOOGLE_DOC_PATTERNS):
                return True

            parsed_url = urlparse(url)
            path = parsed_url.path.lower()

            if '.' in path:
                extension = path.rsplit('.', 1)[-1]
                # Use FileTypeChoices to validate
                return FileTypeChoices.is_valid_extension(extension)

            return False

        except Exception as e:
            logger.error(f"Error checking if URL is document: {e}")
            return False