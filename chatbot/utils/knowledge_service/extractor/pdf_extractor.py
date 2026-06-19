"""PDF extraction functionality"""

import io
import os
import logging
import tempfile
from typing import List, Dict, Any, Tuple

import PyPDF2
from chatbot.utils.knowledge_service.processor.image_processor import HAS_PYMUPDF

logger = logging.getLogger('django')

# Additional imports for enhanced features
if HAS_PYMUPDF:
    import fitz

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
    logger.info("pdfplumber available for enhanced PDF text extraction")
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not available. Using PyMuPDF/PyPDF2 fallback.")


class PDFExtractor:
    """Handles PDF content extraction"""

    def __init__(self, image_processor):
        self.image_processor = image_processor

    def extract_comprehensive_content_for_urls(self, content_bytes: bytes) -> Tuple[str, List[str]]:
        """Extract comprehensive PDF content and hyperlinks using PyMuPDF

        Args:
            content_bytes: PDF file content as bytes

        Returns:
            Tuple of (comprehensive_text, extracted_hyperlinks)
        """
        try:
            if not HAS_PYMUPDF:
                # Fallback to basic text extraction
                text = self.extract_text_enhanced(content_bytes)
                return text, []

            logger.info("=" * 80)
            logger.info("EXTRACTING COMPREHENSIVE PDF CONTENT FOR URL EXTRACTION")
            logger.info("=" * 80)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(content_bytes)
                temp_file_path = temp_file.name

            try:
                doc = fitz.open(temp_file_path)
                text_parts = []
                extracted_hyperlinks = []

                logger.info(f"Processing {len(doc)} pages for content and hyperlinks...")

                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)

                    # Extract text
                    page_text = page.get_text()
                    if page_text.strip():
                        text_parts.append(f"[Page {page_num + 1}]\n{page_text}")

                    # Extract links/annotations
                    links = page.get_links()
                    page_hyperlinks = []

                    for link in links:
                        if 'uri' in link and link['uri']:
                            url = link['uri']
                            if url.startswith('http') and url not in extracted_hyperlinks:
                                extracted_hyperlinks.append(url)
                                page_hyperlinks.append(url)

                    if page_hyperlinks:
                        logger.info(f"  Page {page_num + 1}: {len(page_hyperlinks)} hyperlinks found")
                        for url in page_hyperlinks:
                            logger.info(f"    - {url}")

                doc.close()

                comprehensive_text = '\n'.join(text_parts)

                logger.info(f"PDF extraction complete:")
                logger.info(f"  - Text content: {len(comprehensive_text)} characters")
                logger.info(f"  - Hyperlinks extracted: {len(extracted_hyperlinks)}")

                if extracted_hyperlinks:
                    logger.info("EXTRACTED HYPERLINKS:")
                    for i, url in enumerate(extracted_hyperlinks[:10]):
                        logger.info(f"  URL {i + 1}: {url}")
                    if len(extracted_hyperlinks) > 10:
                        logger.info(f"  ... and {len(extracted_hyperlinks) - 10} more URLs")

                return comprehensive_text, extracted_hyperlinks

            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except Exception as e:
            logger.error(f"Error extracting comprehensive PDF content: {e}")
            # Fallback to basic text extraction
            text = self.extract_text_enhanced(content_bytes)
            return text, []

    def extract_text_enhanced(self, content_bytes: bytes) -> str:
        """Enhanced PDF text extraction with multiple methods

        Args:
            content_bytes: PDF file content as bytes

        Returns:
            Extracted text content
        """
        text = ""

        # Try pdfplumber first if available
        if HAS_PDFPLUMBER:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(content_bytes)
                    temp_file_path = temp_file.name

                try:
                    text_parts = []
                    with pdfplumber.open(temp_file_path) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text and page_text.strip():
                                text_parts.append(page_text)
                    text = '\n'.join(text_parts)
                finally:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)

                if text and len(text.strip()) > 50:
                    logger.info(f"pdfplumber extracted {len(text)} characters")
                    return text
            except Exception as e:
                logger.error(f"pdfplumber failed: {e}")

        # Try PyMuPDF next
        if HAS_PYMUPDF and not text:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(content_bytes)
                    temp_file_path = temp_file.name

                try:
                    doc = fitz.open(temp_file_path)
                    text_parts = []
                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)
                        text_parts.append(page.get_text())
                    text = '\n'.join(text_parts)
                    doc.close()
                finally:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)

                if text and len(text.strip()) > 50:
                    logger.info(f"PyMuPDF extracted {len(text)} characters")
                    return text
            except Exception as e:
                logger.error(f"PyMuPDF failed: {e}")

        # Fallback to PyPDF2
        if not text:
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
                text_parts = []
                for page in pdf_reader.pages:
                    text_parts.append(page.extract_text())
                text = '\n'.join(text_parts)
                logger.info(f"PyPDF2 extracted {len(text)} characters")
            except Exception as e:
                logger.error(f"PyPDF2 failed: {e}")

        # Try OCR if text extraction failed
        if (not text or len(text.strip()) < 50) and self.image_processor.enable_ocr:
            logger.info("Attempting OCR on potentially scanned document")
            ocr_text = self.image_processor.perform_ocr_on_pdf(content_bytes)
            if ocr_text:
                text = text + "\n\n[OCR Content]\n" + ocr_text if text else ocr_text

        return text

    def extract_text(self, file) -> str:
        """Extract text from PDF (fallback method)

        Args:
            file: PDF file object

        Returns:
            Extracted text content
        """
        pdf_reader = PyPDF2.PdfReader(file)
        text_parts = []
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text_parts.append(page.extract_text())
        return '\n'.join(text_parts)