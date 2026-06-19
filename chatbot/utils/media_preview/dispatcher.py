import os
import logging
from .generators import (
    PDFPreviewGenerator,
    DocxPreviewGenerator,
    XlsxPreviewGenerator,
    MarkdownPreviewGenerator,
    CSVPreviewGenerator,
    TxtPreviewGenerator
)
from .constants import THUMB_SIZE

logger = logging.getLogger('django')


class ThumbnailGenerator:
    """Main dispatcher for thumbnail generation"""

    GENERATORS = {
        'pdf': PDFPreviewGenerator,
        'docx': DocxPreviewGenerator,
        'xlsx': XlsxPreviewGenerator,
        'xls': XlsxPreviewGenerator,
        'md': MarkdownPreviewGenerator,
        'markdown': MarkdownPreviewGenerator,
        'csv': CSVPreviewGenerator,
        'txt': TxtPreviewGenerator,
        'text': TxtPreviewGenerator,
    }

    @classmethod
    def register_generator(cls, extension, generator_class):
        """Register a new generator for a file extension"""
        cls.GENERATORS[extension.lower()] = generator_class

    @classmethod
    def generate_preview(cls, file_path, thumbnail=False, thumb_size=THUMB_SIZE):
        """
        Generate preview image for a file
        """
        try:
            ext = os.path.splitext(file_path)[1][1:].lower()

            if ext not in cls.GENERATORS:
                logger.info(f"No generator found for extension: {ext}")
                return None

            generator_class = cls.GENERATORS[ext]
            generator = generator_class(file_path)

            img = generator.generate()

            if img and thumbnail:
                img = generator.create_thumbnail(img, thumb_size)

            return img

        except Exception as e:
            logger.error(f"Error in preview generation for {file_path}: {str(e)}")
            return None

    @classmethod
    def generate_thumbnail(cls, file_path, thumb_size=THUMB_SIZE):
        """
        Convenience method to generate thumbnail directly
        """
        return cls.generate_preview(file_path, thumbnail=True, thumb_size=thumb_size)
