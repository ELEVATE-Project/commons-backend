import logging
import requests
import time
from typing import Dict, Any, Tuple, Optional
from urllib.parse import urlparse
from chatbot.models import FileTypeChoices
from chatbot.utils.knowledge_service.base.extraction_config import DEFAULT_HEADERS, ACCESS_DENIED_PATTERNS
from chatbot.utils.knowledge_service.base.extraction_utils import convert_google_drive_url

logger = logging.getLogger('django')


class DocumentURLProcessor:
    """Handles document downloading and processing from URLs"""

    def __init__(self, url_cache: dict = None, max_file_size_mb: int = 50):
        self.url_cache = url_cache or {}
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = self.max_file_size_mb * 1024 * 1024

    def check_google_access_denial(self, response, download_url: str) -> Optional[Dict[str, Any]]:
        """
        Check if Google Drive/Docs response indicates access denial
        """
        content_type = response.headers.get('content-type', '').lower()

        # Enhanced Google Drive permission detection
        if 'drive.google.com' in download_url or 'docs.google.com' in download_url:
            # Check if response is HTML-like
            if 'html' in content_type or response.text.strip().startswith(
                    '<!DOCTYPE') or response.text.strip().startswith('<html'):
                logger.info(f"Checking for Google access denial in HTML response")
                response_text = response.text[:1000]  # Check first 1000 chars
                logger.info(f"Response preview: {response_text}")

                # Check for access denial patterns
                for pattern in ACCESS_DENIED_PATTERNS:
                    if pattern in response.text:
                        error_info = {
                            'error': f'Permission denied: Cannot access {download_url}',
                            'error_type': 'permission_denied',
                            'status_code': 403,
                            'url': download_url
                        }
                        logger.error(f"Permission denied for URL {download_url} - found pattern: {pattern}")
                        return error_info

        return None

    def validate_file_format(self, url: str, url_extension: str) -> Optional[Dict[str, Any]]:
        """
        Validate file format based on URL extension
        """
        if url_extension and not FileTypeChoices.is_valid_extension(url_extension):
            error_info = {
                'error': f'Unsupported file format: .{url_extension}',
                'error_type': 'unsupported_format',
                'url': url
            }
            logger.error(f"Unsupported file format .{url_extension} for URL {url}")
            return error_info
        return None

    def validate_content_type(self, content_type: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Validate content type for document processing
        """
        # Check if it's HTML content that shouldn't be processed
        if 'html' in content_type and not any(
                indicator in content_type for indicator in ['pdf', 'spreadsheet', 'excel', 'word', 'csv']
        ):
            # This is HTML content, likely an error or sign-in page
            logger.warning(f"Received HTML response for {url}, not processing as document")
            error_info = {
                'error': 'This link returned a web page instead of a document file. This can happen with '
                         'restricted access or unsupported formats',
                'error_type': 'invalid_content_type',
                'url': url
            }
            return error_info
        return None

    def download_document(self, url: str, is_subdoc: bool = False) -> Tuple[
        Optional[bytes], Optional[Dict[str, Any]], str]:
        """
        Download document from URL with error handling
        """
        try:
            logger.info(f"Downloading from: {url} (subdoc: {is_subdoc})")

            # Check cache
            if url in self.url_cache:
                cached_result = self.url_cache[url]
                if isinstance(cached_result, dict) and 'error' in cached_result:
                    return None, cached_result, ""
                if isinstance(cached_result, str):
                    # Return cached text as bytes
                    return cached_result.encode('utf-8'), None, ""
                return cached_result, None, ""

            # Convert Google Drive URLs to downloadable format
            download_url = convert_google_drive_url(url)
            if download_url is None:
                logger.info(f"Skipped non-document URL: {url}")
                return None, None, ""
            if download_url != url:
                logger.info(f"Converted to: {download_url}")

            response = None
            max_retries = 2
            retry_count = 0

            while retry_count < max_retries:
                try:
                    response = requests.get(download_url, headers=DEFAULT_HEADERS,
                                            timeout=60, allow_redirects=True)
                    response.raise_for_status()

                    if response and response.content:
                        content_size = len(response.content)
                        if content_size > self.max_file_size_bytes:
                            content_size_mb = content_size / (1024 * 1024)
                            error_info = {
                                'error': f'File size ({content_size_mb:.2f} MB) exceeds the maximum allowed '
                                         f'size of {self.max_file_size_mb} MB. Please reduce the file size.',
                                'error_type': 'file_size_exceeded',
                                'url': url
                            }
                            logger.error(f"File too large from URL {url}: {content_size_mb:.2f} MB")
                            self.url_cache[url] = error_info
                            return None, error_info, ""
                    break

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 500 and retry_count < max_retries - 1:
                        logger.warning(f"500 error, retrying... (attempt {retry_count + 1})")
                        retry_count += 1
                        time.sleep(2)  # Wait before retry

                        # Try alternative URL format for Google Drive
                        if 'drive.google.com' in download_url and '/d/' in url:
                            file_id = url.split('/d/')[1].split('/')[0]
                            # Try alternative format
                            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                            logger.info(f"Trying alternative URL format: {download_url}")
                    else:
                        raise

                except requests.exceptions.Timeout:
                    if retry_count < max_retries - 1:
                        logger.warning(f"Timeout, retrying... (attempt {retry_count + 1})")
                        retry_count += 1
                        time.sleep(2)
                    else:
                        raise

            if not response:
                raise Exception("Failed to get response after retries")

            # Get content type (THIS IS THE KEY LINE)
            content_type = response.headers.get('content-type', '').lower()
            logger.info(f"Response content_type: {content_type}")

            # Check for Google access denial
            access_error = self.check_google_access_denial(response, download_url)
            if access_error:
                self.url_cache[url] = access_error
                return None, access_error, content_type

            # Validate file format based on URL extension
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()
            url_extension = None

            # Extract extension from URL path
            if '.' in path:
                url_extension = path.rsplit('.', 1)[-1]
                format_error = self.validate_file_format(url, url_extension)
                if format_error:
                    self.url_cache[url] = format_error
                    return None, format_error, content_type

            # Validate content type
            content_error = self.validate_content_type(content_type, url)
            if content_error:
                self.url_cache[url] = content_error
                return None, content_error, content_type

            return response.content, None, content_type

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                error_info = {
                    'error': f'Permission denied accessing {url}',
                    'error_type': 'permission_denied',
                    'status_code': 403,
                    'url': url
                }
            elif e.response.status_code == 404:
                error_info = {
                    'error': f'Document not found at {url}',
                    'error_type': 'not_found',
                    'status_code': 404,
                    'url': url
                }
            else:
                error_info = {
                    'error': f'HTTP error {e.response.status_code} accessing {url}',
                    'error_type': 'http_error',
                    'status_code': e.response.status_code,
                    'url': url
                }
            logger.error(f"HTTP error extracting from URL {url}: {e}")
            self.url_cache[url] = error_info
            return None, error_info, ""

        except requests.exceptions.Timeout:
            error_info = {
                'error': f'Timeout accessing {url}',
                'error_type': 'timeout',
                'url': url
            }
            logger.error(f"Timeout extracting from URL {url}")
            self.url_cache[url] = error_info
            return None, error_info, ""

        except Exception as e:
            error_info = {
                'error': f'Failed to extract from {url}: {str(e)}',
                'error_type': 'extraction_error',
                'url': url
            }
            logger.error(f"Failed to extract from URL {url}: {e}")
            self.url_cache[url] = error_info
            return None, error_info, ""

    def determine_file_type(self, content_bytes: bytes, content_type: str,
                            url: str) -> Tuple[bool, bool, bool, bool, bool]:
        """
        Determine file type from content and metadata
        """
        content_preview = content_bytes[:10] if content_bytes else b''

        is_pdf = content_preview.startswith(b'%PDF') or 'pdf' in content_type
        is_excel = any(indicator in content_type for indicator in ['spreadsheet', 'excel', 'xlsx', 'xls'])
        is_csv = 'csv' in content_type or url.lower().endswith('.csv')
        is_docx = 'word' in content_type or 'document' in content_type or 'officedocument.wordprocessing' in content_type
        is_txt = not any([is_pdf, is_excel, is_csv, is_docx])

        logger.info(f"File type - PDF: {is_pdf}, Excel: {is_excel}, CSV: {is_csv}, DOCX: {is_docx}, TXT: {is_txt}")

        return is_pdf, is_excel, is_csv, is_docx, is_txt