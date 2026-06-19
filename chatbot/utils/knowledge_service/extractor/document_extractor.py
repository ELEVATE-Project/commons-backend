"""Main DocumentExtractor class that coordinates all extraction functionality"""

import io
import logging
import concurrent.futures
from threading import Lock
from typing import Dict, List, Any, Set, Tuple, Generator
from pathlib import Path
from urllib.parse import urlparse
from chatbot.models import FileTypeChoices
from chatbot.utils.knowledge_service.base.extraction_config import MAX_DEPTH
from .docx_extractor import DOCXExtractor
from .excel_extractor import ExcelExtractor
from .markdown_extractor import MarkdownExtractor
from .pdf_extractor import PDFExtractor
from .text_extractor import CSVExtractor, TXTExtractor
from .url_extractor import URLExtractor
from chatbot.utils.knowledge_service.processor.url_processor import DocumentURLProcessor
from chatbot.utils.knowledge_service.processor.image_processor import ImageProcessor
from chatbot.utils.knowledge_service.processor.ai_processor import AIContentProcessor
from chatbot.utils.knowledge_service.base.extraction_utils import (
    normalize_url_for_tracking, get_comprehensive_content_for_url_extraction, convert_google_drive_url
)


logger = logging.getLogger('django')


class DocumentExtractor:
    """
    Extract structured content from documents using AWS Bedrock Llama model with enhanced features
    """

    def __init__(
            self, max_depth: int = MAX_DEPTH, max_subdocs: int = 10, enable_ocr: bool = True,
            compress_images: bool = True, extract_images: bool = False, main_doc_max_chars: int = 3000,
            subdoc_max_chars: int = 500, excel_max_rows: int = 50, excel_max_cols: int = 20,
            max_file_size_mb: int = 50, max_workers: int = 5
    ):
        """Initialize with enhanced features and configurable limits"""
        self.max_depth = max_depth
        self.max_subdocs = max_subdocs
        self.processed_urls: Set[str] = set()
        self.url_cache: Dict[str, str] = {}
        self.enable_ocr = enable_ocr
        self.compress_images = compress_images
        self.extract_images = extract_images  # Control image extraction

        # Configurable text limits
        self.main_doc_max_chars = main_doc_max_chars
        self.subdoc_max_chars = subdoc_max_chars
        self.excel_max_rows = excel_max_rows
        self.excel_max_cols = excel_max_cols

        # File validation
        self.allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.csv', '.xls', '.xlsx'}
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = self.max_file_size_mb * 1024 * 1024

        # Parallel processing
        self.max_workers = max_workers
        self.url_lock = Lock()

        # Initialize components
        self.url_extractor = URLExtractor()
        self.url_processor = DocumentURLProcessor(self.url_cache, max_file_size_mb)
        self.image_processor = ImageProcessor(enable_ocr, compress_images, extract_images)
        self.ai_processor = AIContentProcessor(main_doc_max_chars)

        # Initialize file extractors
        self.pdf_extractor = PDFExtractor(self.image_processor)
        self.docx_extractor = DOCXExtractor(self.image_processor)
        self.excel_extractor = ExcelExtractor(excel_max_rows, excel_max_cols, subdoc_max_chars)  # Legacy, kept for compatibility
        self.markdown_extractor = MarkdownExtractor(subdoc_max_chars)  # Used for Excel/CSV to Markdown conversion
        self.csv_extractor = CSVExtractor(excel_max_rows, excel_max_cols)  # Legacy, kept for compatibility
        self.txt_extractor = TXTExtractor()

    def process_single_subdocument(self, sub_url: str, main_doc_url: str,
                                 company_bot, other_data) -> Dict[str, Any]:
        """Process a single subdocument - used for parallel processing"""
        try:
            # Extract content from subdocument URL
            sub_text, sub_images, sub_media_type, sub_error_info, _ = self.extract_text_from_url(
                sub_url, is_subdoc=True
            )

            if sub_error_info:
                logger.info(f"Subdocument failed: {sub_error_info}")

                # Enhance error message for unsupported formats
                if sub_error_info.get('error_type') == 'unsupported_format':
                    sub_error_info['error'] = f"Unsupported file format in linked document: {sub_error_info['error']}"

                return {
                    'success': False,
                    'error': {
                        "file_url": sub_url,
                        "error": sub_error_info,
                        "source_document": main_doc_url
                    }
                }

            # Successfully accessed - process subdocument with LLM
            if sub_text and len(sub_text.strip()) > 10:
                # Get the downloadable URL
                downloadable_url = convert_google_drive_url(sub_url)

                # Check if media type was determined
                if sub_media_type is None:
                    logger.warning(f"Could not determine valid media type for {sub_url}")
                    return {
                        'success': False,
                        'error': {
                            "file_url": sub_url,
                            "error": {
                                'error': 'Could not determine valid file type',
                                'error_type': 'unknown_format',
                                'url': sub_url
                            },
                            "source_document": main_doc_url
                        }
                    }

                # Process subdocument content with Bedrock
                subdoc_result = self.ai_processor.extract_basic_content(
                    sub_text,
                    company_bot,
                    sub_images,
                    other_data,
                    is_subdoc=True
                )

                # Check for any extraction errors in subdocument
                if (subdoc_result.get('title_extraction_failed') or
                        subdoc_result.get('extraction_error') or
                        subdoc_result.get('error') or
                        subdoc_result.get('error_type')):
                    error_message = (subdoc_result.get('error') or
                                   subdoc_result.get('extraction_error') or
                                   'LLM failed to extract title from subdocument')

                    error_type = (subdoc_result.get('error_type') or
                                'title_extraction_failed')

                    logger.error(f"Subdocument extraction failed for {sub_url}: {error_message}")
                    return {
                        'success': False,
                        'error': {
                            "file_url": sub_url,
                            "error": {
                                'error': error_message,
                                'error_type': error_type,
                                'url': sub_url
                            },
                            "source_document": main_doc_url
                        }
                    }

                # Create subdocument entry (without "url" field)
                subdoc_entry = {
                    "title": subdoc_result.get(
                        "title",
                        f"Document from {Path(urlparse(main_doc_url).path).name or 'linked document'}"
                    ),
                    "file_url": downloadable_url,
                    "media_type": sub_media_type,
                    "source_document": main_doc_url,
                    "exact_content": sub_text,
                    "summary": subdoc_result.get("summary", ""),
                    "tags": subdoc_result.get("tags", []),
                    "organization": subdoc_result.get("organization", ""),
                    "document_type": subdoc_result.get("document_type", ""),
                    "key_entities": subdoc_result.get("key_entities", []),
                    "subdocument": [],
                    "images": sub_images or []
                }

                return {'success': True, 'data': subdoc_entry}
            else:
                logger.warning(f"Subdocument {sub_url} has insufficient content")
                return {
                    'success': False,
                    'error': {
                        "file_url": sub_url,
                        "error": {
                            'error': 'Document has insufficient content (less than 10 characters)',
                            'error_type': 'insufficient_content',
                            'url': sub_url
                        },
                        "source_document": main_doc_url
                    }
                }
        except Exception as e:
            logger.error(f"Error processing subdocument {sub_url}: {str(e)}")
            return {
                'success': False,
                'error': {
                    "file_url": sub_url,
                    "error": {"error": str(e), "error_type": "processing_error"},
                    "source_document": main_doc_url
                }
            }

    def process_subdocuments_parallel(self, subdoc_urls: List[str], main_doc_url: str,
                                    company_bot, other_data) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process subdocuments in parallel"""
        subdocuments = []
        failed_links = []

        # Limit subdocuments to max_subdocs
        urls_to_process = subdoc_urls[:self.max_subdocs]

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all subdocument processing tasks
            future_to_url = {
                executor.submit(
                    self.process_single_subdocument,
                    url, main_doc_url, company_bot, other_data
                ): url
                for url in urls_to_process
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result['success']:
                        subdocuments.append(result['data'])
                    else:
                        failed_links.append(result['error'])
                except Exception as e:
                    logger.error(f"Exception processing subdocument {url}: {str(e)}")
                    failed_links.append({
                        "file_url": url,
                        "error": {"error": str(e), "error_type": "processing_error"},
                        "source_document": main_doc_url
                    })

        return subdocuments, failed_links

    def extract_urls_memory_efficient(self, text: str) -> Generator[str, None, None]:
        """Extract URLs using a memory-efficient generator approach"""
        # Process text in chunks to avoid memory issues with large documents
        chunk_size = 10000  # 10k characters per chunk

        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            # Ensure we don't cut URLs in half - extend to next whitespace
            if i + chunk_size < len(text):
                next_space = text.find(' ', i + chunk_size)
                if next_space != -1:
                    chunk = text[i:next_space]

            # Extract URLs from this chunk
            urls = self.url_extractor.extract_urls_from_text(chunk)
            for url in urls:
                yield url

    def process_text_sections_generator(self, sections: List[str]) -> Generator[str, None, None]:
        """Process text sections using a generator to save memory"""
        for section in sections:
            # Process section
            processed = section.strip()
            if processed:
                yield processed
            # Free memory after yielding
            del section

    def _extract_content_from_bytes(
            self,
            content_bytes: bytes,
            file_extension: str,
            extract_mode: str = "full"
    ) -> Tuple[str, List[Dict[str, Any]], str, List[str], Any]:
        """Internal method to extract content from file bytes"""
        file_extension = file_extension.lower().strip('.')
        text = ""
        images = []
        comprehensive_text = ""
        hyperlinks = []
        media_type = None

        skip_text = extract_mode == "urls_only"
        skip_urls = extract_mode == "limited"

        if file_extension == 'pdf':
            if not skip_urls:
                comprehensive_text, hyperlinks = self.pdf_extractor.extract_comprehensive_content_for_urls(
                    content_bytes)

            if not skip_text:
                if extract_mode == "full":
                    text = comprehensive_text
                else:
                    text = self.pdf_extractor.extract_text_enhanced(content_bytes)

                max_chars = self.subdoc_max_chars if extract_mode == "limited" else self.main_doc_max_chars
                if len(text) > max_chars:
                    text = text[:max_chars] + "\n...[Content truncated for LLM]"

                if self.extract_images:
                    images = self.image_processor.extract_images_from_pdf_pymupdf(content_bytes)

            media_type = FileTypeChoices.PDF

        elif file_extension in ['doc', 'docx']:
            if not skip_urls:
                comprehensive_text, hyperlinks = self.docx_extractor.extract_comprehensive_content_for_urls(
                    content_bytes)

            if not skip_text:
                import tempfile
                import os
                import docx

                with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
                    temp_file.write(content_bytes)
                    temp_file_path = temp_file.name

                try:
                    doc = docx.Document(temp_file_path)
                    text_parts = []
                    for para in doc.paragraphs:
                        if para.text.strip():
                            text_parts.append(para.text)
                    text = '\n'.join(self.process_text_sections_generator(text_parts))

                    max_chars = self.subdoc_max_chars if extract_mode == "limited" else self.main_doc_max_chars
                    if len(text) > max_chars:
                        text = text[:max_chars] + "\n...[Content truncated for LLM]"

                finally:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)

                if self.extract_images:
                    images = self.image_processor.extract_images_from_docx(content_bytes)

            media_type = FileTypeChoices.DOCX

        elif file_extension in ['xls', 'xlsx']:
            # Excel files are converted to Markdown format using MarkdownExtractor
            # This provides better structured output for LLM processing compared to CSV or pandas string format
            # The MarkdownExtractor uses tabulate library to create clean Markdown tables
            filename = f"spreadsheet.{file_extension}"

            if not skip_urls:
                # Extract comprehensive content for URL extraction (no character limits)
                # Also extracts hyperlinks embedded in Excel cells using openpyxl
                # Called when: extract_mode = "full" or "urls_only"
                comprehensive_text, hyperlinks = self.markdown_extractor.extract_comprehensive_content_for_urls(
                    content_bytes, filename)

            if not skip_text:
                # Extract limited content for LLM processing (with character limits)
                # Converts Excel sheets to Markdown tables with proper formatting
                # Called when: extract_mode = "full" or "limited" (subdocuments)
                max_chars = self.subdoc_max_chars if extract_mode == "limited" else self.main_doc_max_chars
                text = self.markdown_extractor.extract_limited_content(content_bytes, max_chars, filename)

            media_type = FileTypeChoices.XLSX

        elif file_extension == 'csv':
            # Use MarkdownExtractor for better CSV to Markdown conversion
            filename = "spreadsheet.csv"

            if not skip_urls:
                # Extract comprehensive content for URL extraction (no character limits)
                # Converts entire CSV to Markdown format for URL scanning
                # Called when: extract_mode = "full" or "urls_only"
                comprehensive_text, hyperlinks = self.markdown_extractor.extract_comprehensive_content_for_urls(
                    content_bytes, filename)

            if not skip_text:
                # Extract limited content for LLM processing (with character limits)
                # Converts CSV to Markdown table with proper formatting
                # Called when: extract_mode = "full" or "limited" (subdocuments)
                max_chars = self.subdoc_max_chars if extract_mode == "limited" else self.main_doc_max_chars
                text = self.markdown_extractor.extract_limited_content(content_bytes, max_chars, filename)

            media_type = FileTypeChoices.CSV

        elif file_extension == 'txt':
            if not skip_urls:
                comprehensive_text, hyperlinks = self.txt_extractor.extract_comprehensive_content_for_urls(
                    content_bytes)

            if not skip_text:
                text = content_bytes.decode('utf-8', errors='ignore')

                max_chars = self.subdoc_max_chars if extract_mode == "limited" else self.main_doc_max_chars
                if len(text) > max_chars:
                    text = text[:max_chars] + "\n...[Content truncated for LLM]"

            media_type = FileTypeChoices.TXT

        else:
            text = content_bytes.decode('utf-8', errors='ignore')
            comprehensive_text = text

        if hyperlinks:
            comprehensive_text = comprehensive_text + "\n\n=== EXTRACTED HYPERLINKS ===\n" + "\n".join(hyperlinks)

        return text, images, comprehensive_text, hyperlinks, media_type

    def extract_text_from_url(self, url: str, is_subdoc: bool = False, is_source_doc: bool = False) -> Tuple[
        str, List[Dict[str, Any]], Any, Dict[str, Any], str]:
        """Extract text content and images from document URL"""

        try:
            # Download document
            content_bytes, error_info, content_type = self.url_processor.download_document(url, is_subdoc)

            if error_info:
                return "", [], None, error_info, ""

            if not content_bytes:
                return "", [], None, None, ""

            is_pdf, is_excel, is_csv, is_docx, is_txt = self.url_processor.determine_file_type(
                content_bytes, content_type, url
            )

            # Determine file extension
            if is_pdf:
                file_ext = 'pdf'
            elif is_excel:
                file_ext = 'xlsx'
            elif is_csv:
                file_ext = 'csv'
            elif is_docx:
                file_ext = 'docx'
            else:
                file_ext = 'txt'

            # Determine extraction mode
            if is_source_doc:
                extract_mode = "urls_only"
            elif is_subdoc:
                extract_mode = "limited"
            else:
                extract_mode = "full"

            # Use unified extraction method
            text, images, full_text_for_url_extraction, extracted_hyperlinks, media_type = self._extract_content_from_bytes(
                content_bytes, file_ext, extract_mode
            )

            # URL extraction logic (memory-efficient for large docs)
            combined_urls = list(extracted_hyperlinks)
            if len(full_text_for_url_extraction) > 50000:
                seen_urls = set(combined_urls)
                for url_found in self.extract_urls_memory_efficient(full_text_for_url_extraction):
                    if url_found not in seen_urls:
                        combined_urls.append(url_found)
                        seen_urls.add(url_found)
            else:
                text_urls = self.url_extractor.extract_urls_from_text(full_text_for_url_extraction)
                for url_found in text_urls:
                    if url_found not in combined_urls:
                        combined_urls.append(url_found)

            # Logging
            logger.info(f"URL extraction summary for {url}:")
            logger.info(f"  - Hyperlinks extracted: {len(extracted_hyperlinks)}")
            logger.info(f"  - Total unique URLs: {len(combined_urls)}")

            # Apply character limit for subdocuments
            if is_subdoc:
                max_chars = self.subdoc_max_chars
                if len(text) > max_chars:
                    text = text[:max_chars] + "\n...[Content truncated]"

            # Validation (skip for source docs)
            if not is_source_doc and (not text or len(text.strip()) < 10):
                logger.warning(f"No meaningful content extracted from {url}")
                error_info = {
                    'error': f'No content could be extracted from {url}',
                    'error_type': 'no_content',
                    'url': url
                }
                return "", [], None, error_info, ""

            if text:
                self.url_cache[url] = text

            logger.info(f"Extracted {len(text)} chars, {len(images)} images from {url}")

            return text, images, media_type, None, full_text_for_url_extraction

        except Exception as e:
            error_info = {
                'error': f'Failed to extract from {url}: {str(e)}',
                'error_type': 'extraction_error',
                'url': url
            }
            logger.error(f"Failed to extract from URL {url}: {e}")
            return "", [], None, error_info, ""

    def extract_text_from_file(self, file, file_extension: str):
        """Extract text content and images from various file types"""

        try:
            file_extension = file_extension.lower().strip('.')

            # Read file bytes
            if isinstance(file, (str, Path)):
                file_path = Path(file)
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_path}")
                with open(file_path, 'rb') as f:
                    content_bytes = f.read()
            else:
                # File object
                file.seek(0)
                content_bytes = file.read()
                if not isinstance(content_bytes, bytes):
                    content_bytes = content_bytes.encode('utf-8')

            # Use unified extraction method (full mode for local files)
            text, images, comprehensive_text, hyperlinks, media_type = self._extract_content_from_bytes(
                content_bytes, file_extension, extract_mode="full"
            )

            logger.info(f"Extracted from file: {len(text)} chars, {len(comprehensive_text)} comprehensive chars")

            return text, images, comprehensive_text, media_type

        except Exception as e:
            logger.error(f"Error extracting from file: {e}")
            return "", [], ""

    def read_document(self, file_path: str) -> str:
        """Extract text content from various document formats"""
        file_path = Path(file_path)
        file_ext = file_path.suffix.lower().strip('.')

        try:
            text, _, _, _ = self.extract_text_from_file(file_path, file_ext)
            return text
        except Exception as e:
            raise Exception(f"Error reading document: {str(e)}")

    def process_document_with_links(
        self, text: str, company_bot, comprehensive_text: str = None, processed_urls=None,
        depth=0, max_depth=MAX_DEPTH, extracted_images: List[Dict[str, Any]] = None, other_data=None
) -> Dict[str, Any]:
        """Process document and extract links from linked documents with enhanced URL extraction for ALL formats"""
        if processed_urls is None:
            processed_urls = set()

        try:
            # Step 1: Extract basic content from current document using Bedrock
            logger.info(f"{'  ' * depth}Processing main document with Bedrock...")
            main_result = self.ai_processor.extract_basic_content(text, company_bot, extracted_images, other_data)

            # Use comprehensive text for URL extraction
            url_extraction_text = comprehensive_text if comprehensive_text else text

            # Step 2: Extract URLs from comprehensive document content
            logger.info(f"{'  ' * depth}Extracting URLs from main document...")
            logger.info(f"{'  ' * depth}  - Using comprehensive content: {len(url_extraction_text)} chars")
            logger.info(f"{'  ' * depth}  - Limited text for LLM: {len(text)} chars")

            # Memory-efficient URL extraction for large documents
            if len(url_extraction_text) > 50000:
                urls = list(self.extract_urls_memory_efficient(url_extraction_text))
            else:
                urls = self.url_extractor.extract_urls_from_text(url_extraction_text)

            main_result["url"] = urls

            # Log all extracted URLs
            logger.info(f"{'  ' * depth}Total URLs extracted from main document: {len(urls)}")

            # Step 3: Process links
            subdocuments = []
            failed_links = []
            source_documents = []  # NEW: List for source documents

            # Filter for document URLs
            document_urls = [url for url in urls if self.url_extractor.is_document_url(url, depth)]
            logger.info(f"{'  ' * depth}Found {len(document_urls)} document URLs in main document")

            # Process first level of linked documents
            first_level_results = []
            for main_doc_url in document_urls:
                # Normalize URL for deduplication
                normalized_url = normalize_url_for_tracking(main_doc_url)

                if normalized_url in processed_urls:
                    logger.info(f"{'  ' * depth}Skipping already processed URL: {main_doc_url}")
                    continue

                logger.info(f"{'  ' * depth}Processing linked document: {main_doc_url}")
                processed_urls.add(normalized_url)

                # Extract content from this linked document
                linked_text, linked_images, linked_media_type, error_info, full_text_for_urls = self.extract_text_from_url(
                    main_doc_url, is_source_doc=True
                )

                if error_info:
                    # Enhanced error handling for different error types
                    if error_info.get('error_type') == 'unsupported_format':
                        error_info['error'] = f"Unsupported file format: {error_info['error']}"

                    failed_links.append({
                        "file_url": main_doc_url,
                        "error": error_info,
                        "source_document": "main"
                    })
                    continue

                if full_text_for_urls and len(full_text_for_urls.strip()) > 10:
                    # Check if media type was determined
                    if linked_media_type is None:
                        logger.warning(f"Could not determine valid media type for {main_doc_url}")
                        failed_links.append({
                            "file_url": main_doc_url,
                            "error": {
                                'error': 'Could not determine valid file type',
                                'error_type': 'unknown_format',
                                'url': main_doc_url
                            },
                            "source_document": "main"
                        })
                        continue

                    # NEW: Add source document entry with URL and exact content
                    source_documents.append({
                        "url": main_doc_url,
                        "exact_content": full_text_for_urls  # Markdown content for Excel/CSV, full text for others
                    })

                    first_level_results.append({
                        'main_doc_url': main_doc_url,
                        'linked_text': linked_text,
                        'linked_images': linked_images,
                        'linked_media_type': linked_media_type,
                        'full_text_for_urls': full_text_for_urls
                    })
                else:
                    logger.warning(f"Linked document {main_doc_url} has insufficient content: {linked_text}")
                    failed_links.append({
                        "file_url": main_doc_url,
                        "error": {
                            'error': 'Document has insufficient content (less than 10 characters)',
                            'error_type': 'insufficient_content',
                            'url': main_doc_url
                        },
                        "source_document": "main"
                    })

            # Process subdocuments in parallel for each first-level document
            for first_level_doc in first_level_results:
                main_doc_url = first_level_doc['main_doc_url']
                full_text_for_urls = first_level_doc['full_text_for_urls']

                # Extract URLs from the comprehensive content
                logger.info(f"{'  ' * depth}Extracting URLs from linked document: {main_doc_url}")
                logger.info(f"{'  ' * depth}  - Using comprehensive content: {len(full_text_for_urls)} chars")

                # Memory-efficient URL extraction
                if len(full_text_for_urls) > 50000:
                    links_in_subdoc = list(self.extract_urls_memory_efficient(full_text_for_urls))
                else:
                    links_in_subdoc = self.url_extractor.extract_urls_from_text(full_text_for_urls)

                logger.info(f"{'  ' * depth}Found {len(links_in_subdoc)} total links inside {main_doc_url}")

                # Filter for document URLs
                subdoc_document_urls = [url for url in links_in_subdoc if self.url_extractor.is_document_url(url, depth)]
                logger.info(f"{'  ' * depth}Found {len(subdoc_document_urls)} document URLs inside {main_doc_url}")

                # Filter out already processed URLs
                urls_to_process = []
                for sub_url in subdoc_document_urls:
                    normalized_sub_url = normalize_url_for_tracking(sub_url)

                    with self.url_lock:
                        if normalized_sub_url not in processed_urls:
                            processed_urls.add(normalized_sub_url)
                            urls_to_process.append(sub_url)

                # Process subdocuments in parallel
                if urls_to_process:
                    logger.info(f"{'  ' * depth}Processing {len(urls_to_process)} subdocuments in parallel...")
                    subdocs, failed = self.process_subdocuments_parallel(
                        urls_to_process, main_doc_url, company_bot, other_data
                    )
                    subdocuments.extend(subdocs)
                    failed_links.extend(failed)

            main_result["subdocument"] = subdocuments
            main_result["failed_links"] = failed_links
            main_result["source_document"] = source_documents  # NEW: Add source documents to result

            # Log summary
            logger.info(f"{'  ' * depth}Processing complete:")
            logger.info(f"{'  ' * depth}  - URLs in main document: {len(urls)}")
            logger.info(f"{'  ' * depth}  - Document URLs in main: {len(document_urls)}")
            logger.info(f"{'  ' * depth}  - Source documents: {len(source_documents)}")  # NEW
            logger.info(f"{'  ' * depth}  - Successfully processed subdocuments: {len(subdocuments)}")
            logger.info(f"{'  ' * depth}  - Failed: {len(failed_links)}")
            logger.info(f"{'  ' * depth}  - Total URLs processed: {len(processed_urls)}")

            return main_result

        except ValueError as ve:
            logger.error(f"Main document processing failed: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "title": "",
                "organization": "",
                "tags": [],
                "exact_content": text,
                "summary": "",
                "document_type": "",
                "key_entities": [],
                "url": [],
                "subdocument": [],
                "failed_links": [],
                "source_document": [],  # NEW
                "images": extracted_images or []
            }

    def extract_with_bedrock(self, document_text, company_bot,
                         extracted_images: List[Dict[str, Any]] = None,
                         other_data=None) -> Dict[str, Any]:
        try:
            logger.info("Starting document processing with recursive link extraction...")

            # Get comprehensive content for URL extraction
            comprehensive_text_for_urls = get_comprehensive_content_for_url_extraction(
                document_text, other_data
            )

            result = self.process_document_with_links(
                text=document_text,  # Limited text for LLM
                comprehensive_text=comprehensive_text_for_urls,  # Full text for URL extraction
                company_bot=company_bot,
                extracted_images=extracted_images,
                other_data=other_data
            )
            return result
        except ValueError as ve:
            # Re-raise ValueError so it can be handled by the calling function
            logger.error(f"Document processing validation failed: {str(ve)}")
            raise  # This allows the error to propagate to get_doc_tags_from_ai()
        except Exception as e:
            logger.error(f"Document processing failed with unexpected error: {str(e)}")
            return {
                "title": "",
                "organization": "",
                "tags": [],
                "summary": "",
                "document_type": "",
                "key_entities": [],
                "url": [],
                "subdocument": [],
                "source_document": [],  # NEW
                "images": extracted_images or []
            }

    def extract_with_llm(self, text: str, company_bot=None, max_chars: int = 6000,
                         extracted_images: List[Dict[str, Any]] = None, other_data=None) -> Dict[str, Any]:
        """Extract structured information using AWS Bedrock Llama"""
        # Don't truncate - preserve complete content
        return self.extract_with_bedrock(
            document_text=text, company_bot=company_bot,
            extracted_images=extracted_images, other_data=other_data
        )

    def process_document_from_url(self, url: str, company_bot=None) -> Dict[str, Any]:
        """Process document directly from URL"""
        try:
            text_content, extracted_images, extracted_media_type, error_info, _ = self.extract_text_from_url(
                url, is_subdoc=False
            )

            if error_info:
                return {
                    "error": error_info['error'],
                    "error_type": error_info.get('error_type', 'unknown'),
                    "file_path": url,
                    "file_name": Path(url).name,
                }

            if not text_content or len(text_content.strip()) < 10:
                raise ValueError("Document appears to be empty or unreadable")

            extracted_info = self.extract_with_llm(text_content, company_bot, extracted_images=extracted_images)

            result = {
                "file_path": url,
                "file_name": Path(url).name,
                "text_length": len(text_content),
                **extracted_info
            }

            return result

        except Exception as e:
            return {
                "error": str(e),
                "file_path": url,
                "file_name": "Unknown",
            }

    def process_document(self, file_path: str, company_bot=None, other_data=None) -> Dict[str, Any]:
        """Process document from file path"""
        try:
            # Read document content with enhanced extraction
            text_content, extracted_images, comprehensive_text_for_urls, _ = self.extract_text_from_file(
                file_path, Path(file_path).suffix.strip('.')
            )

            if not text_content or len(text_content.strip()) < 10:
                raise ValueError("Document appears to be empty or unreadable")

            # Extract structured information using LLM
            extracted_info = self.extract_with_llm(
                text=text_content,
                company_bot=company_bot,
                extracted_images=extracted_images,
                other_data=other_data,
            )

            # Add metadata
            result = {
                "file_path": str(file_path),
                "file_name": Path(file_path).name,
                "text_length": len(text_content),
                **extracted_info
            }

            return result

        except Exception as e:
            return {
                "error": str(e),
                "file_path": str(file_path),
                "file_name": Path(file_path).name if Path(file_path).exists() else "Unknown",
            }