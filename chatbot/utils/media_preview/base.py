from abc import ABC, abstractmethod
from PIL import Image, ImageDraw, ImageFont
from .constants import THUMB_SIZE, DEFAULT_IMG_SIZE, DEFAULT_BG_COLOR, DEFAULT_TEXT_COLOR, TEXT_PADDING
import logging

logger = logging.getLogger('django')


class BasePreviewGenerator(ABC):
    """Base class for all preview generators"""

    def __init__(self, file_path):
        self.file_path = file_path
        self.img_size = DEFAULT_IMG_SIZE
        self.bg_color = DEFAULT_BG_COLOR
        self.text_color = DEFAULT_TEXT_COLOR

    @abstractmethod
    def extract_content(self):
        """Extract content from the file to be rendered"""
        pass

    def create_text_image(self, text, max_chars=1200):
        """Create an image with text content"""
        img = Image.new("RGB", self.img_size, self.bg_color)
        draw = ImageDraw.Draw(img)

        display_text = text[:max_chars]
        if len(text) > max_chars:
            display_text += "..."

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except:
            font = ImageFont.load_default()

        draw.text((TEXT_PADDING, TEXT_PADDING), display_text, fill=self.text_color, font=font)
        return img

    def create_thumbnail(self, img, size=THUMB_SIZE):
        """Create thumbnail from image - returns a new image object"""
        thumb = img.copy()
        thumb.thumbnail(size)
        return thumb

    def generate(self):
        """Main method to generate preview image"""
        try:
            content = self.extract_content()
            img = self.create_image(content)
            return img
        except Exception as e:
            logger.error(f"Error generating preview for {self.file_path}: {str(e)}")
            return None

    def create_image(self, content):
        """Create image from content - can be overridden"""
        return self.create_text_image(content)
