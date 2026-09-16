import io
import os
import base64
import logging
import tempfile
from typing import List, Dict, Any

logger = logging.getLogger('django')

# Check for optional image processing libraries
try:
    import fitz  # PyMuPDF for better PDF handling

    HAS_PYMUPDF = True
    logger.info("PyMuPDF available for enhanced PDF processing")
except ImportError:
    HAS_PYMUPDF = False
    logger.warning("PyMuPDF not available. Using PyPDF2 for text extraction only.")

try:
    from PIL import Image

    HAS_PIL = True
    logger.info("PIL available for image processing")
except ImportError:
    HAS_PIL = False
    logger.warning("PIL not available. Image processing will be limited.")

try:
    import pytesseract
    from PIL import Image as PILImage

    HAS_OCR = True
    logger.info("pytesseract available for OCR processing")
except ImportError:
    HAS_OCR = False
    logger.warning("pytesseract not available. Scanned document processing will be limited.")


class ImageProcessor:
    """Handles image extraction and processing from documents"""

    def __init__(self, enable_ocr: bool = True, compress_images: bool = True,
                 extract_images: bool = False):
        """Initialize image processor

        Args:
            enable_ocr: Enable OCR processing
            compress_images: Compress images before encoding
            extract_images: Enable image extraction from documents
        """
        self.enable_ocr = enable_ocr and HAS_OCR
        self.compress_images = compress_images
        self.extract_images = extract_images

    def image_to_base64(self, image_bytes: bytes, image_format: str = "PNG") -> str:
        """Convert image bytes to base64 string

        Args:
            image_bytes: Raw image bytes
            image_format: Image format (PNG, JPEG, etc.)

        Returns:
            Base64 encoded image string
        """
        try:
            if HAS_PIL and self.compress_images:
                # Use PIL to potentially optimize/convert image
                image = Image.open(io.BytesIO(image_bytes))
                buffer = io.BytesIO()

                # Convert to RGB if necessary
                if image.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = background

                # Resize if too large
                max_dimension = 1024
                if max(image.size) > max_dimension:
                    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

                image.save(buffer, format="JPEG", quality=85, optimize=True)
                image_bytes = buffer.getvalue()

            # Encode to base64
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            mime_type = f"image/{image_format.lower()}"
            return f"data:{mime_type};base64,{base64_string}"

        except Exception as e:
            logger.error(f"Error converting image to base64: {e}")
            return ""

    def extract_images_from_pdf_pymupdf(self, content_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract images from PDF using PyMuPDF

        Args:
            content_bytes: PDF file content as bytes

        Returns:
            List of extracted images with metadata
        """
        images = []

        # Check if image extraction is enabled
        if not self.extract_images:
            return images

        if not HAS_PYMUPDF:
            return images

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(content_bytes)
                temp_file_path = temp_file.name

            try:
                doc = fitz.open(temp_file_path)

                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    image_list = page.get_images()

                    max_images_per_page = 10

                    for img_index, img in enumerate(image_list[:max_images_per_page]):
                        try:
                            xref = img[0]
                            pix = fitz.Pixmap(doc, xref)

                            # Skip very small images
                            if pix.width < 100 or pix.height < 100:
                                pix = None
                                continue

                            # Skip very large images
                            if pix.width * pix.height > 2048 * 2048:
                                pix = None
                                continue

                            # Convert to PNG bytes
                            if pix.n - pix.alpha < 4:  # GRAY or RGB
                                img_bytes = pix.tobytes("png")
                                base64_image = self.image_to_base64(img_bytes, "PNG")

                                if base64_image:
                                    images.append({
                                        "page": page_num + 1,
                                        "index": img_index,
                                        "width": pix.width,
                                        "height": pix.height,
                                        "base64": base64_image,
                                        "format": "png"
                                    })

                            pix = None

                        except Exception as e:
                            logger.error(f"Error extracting image {img_index} from page {page_num + 1}: {e}")

                    if len(images) > 50:
                        logger.warning("Reached maximum image limit (50)")
                        break

                doc.close()

            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

            logger.info(f"Extracted {len(images)} images from PDF")
            return images

        except Exception as e:
            logger.error(f"Error extracting images from PDF: {e}")
            return []

    def extract_images_from_docx(self, content_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract images from DOCX file

        Args:
            content_bytes: DOCX file content as bytes

        Returns:
            List of extracted images with metadata
        """
        images = []

        # Check if image extraction is enabled
        if not self.extract_images:
            return images

        try:
            import docx

            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
                temp_file.write(content_bytes)
                temp_file_path = temp_file.name

            try:
                doc = docx.Document(temp_file_path)

                image_count = 0
                for rel in doc.part.rels.values():
                    if "image" in rel.target_ref:
                        try:
                            image_part = rel.target_part
                            image_bytes = image_part.blob

                            if len(image_bytes) < 1000:
                                continue

                            content_type = image_part.content_type
                            image_format = "PNG"
                            if "jpeg" in content_type or "jpg" in content_type:
                                image_format = "JPEG"

                            base64_image = self.image_to_base64(image_bytes, image_format)

                            if base64_image:
                                images.append({
                                    "index": image_count,
                                    "base64": base64_image,
                                    "format": image_format.lower()
                                })
                                image_count += 1

                        except Exception as e:
                            logger.error(f"Error extracting image from DOCX: {e}")

            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

            logger.info(f"Extracted {len(images)} images from DOCX")
            return images

        except Exception as e:
            logger.error(f"Error extracting images from DOCX: {e}")
            return []

    def perform_ocr_on_pdf(self, content_bytes: bytes) -> str:
        """Perform OCR on scanned PDF pages

        Args:
            content_bytes: PDF file content as bytes

        Returns:
            Extracted text from OCR
        """
        if not self.enable_ocr or not HAS_PYMUPDF:
            return ""

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(content_bytes)
                temp_file_path = temp_file.name

            try:
                doc = fitz.open(temp_file_path)
                ocr_text_parts = []

                for page_num in range(min(10, len(doc))):
                    page = doc.load_page(page_num)

                    # Check if page has extractable text
                    page_text = page.get_text()
                    if len(page_text.strip()) > 50:
                        continue

                    # Convert page to image for OCR
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("png")

                    # Perform OCR
                    image = PILImage.open(io.BytesIO(img_data))
                    ocr_text = pytesseract.image_to_string(image, lang='eng')

                    if ocr_text.strip():
                        ocr_text_parts.append(f"[Page {page_num + 1} - OCR]\n{ocr_text}")

                    pix = None

                doc.close()
                return '\n\n'.join(ocr_text_parts)

            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except Exception as e:
            logger.error(f"Error performing OCR: {e}")
            return ""