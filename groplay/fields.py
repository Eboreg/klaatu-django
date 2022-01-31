import io
import logging
from typing import Optional, Tuple

from PIL import Image

from django.db import models
from django.db.models.fields.files import ImageFieldFile

logger = logging.getLogger(__name__)


class ResizeImageFieldFile(ImageFieldFile):
    """Resize large images, silently report error on fail"""
    max_width: Optional[int]
    max_height: Optional[int]

    def __init__(self, instance, field, name):
        self.max_height, self.max_width = field.max_height, field.max_width
        super().__init__(instance, field, name)

    def get_target_size(self, image: Image.Image) -> Tuple[int, int]:
        width_divider = image.width / (self.max_width or image.width)
        height_divider = image.height / (self.max_height or image.height)
        divider = max([width_divider, height_divider])
        return int(image.width / divider), int(image.height / divider)

    def should_resize(self, image) -> bool:
        return (self.max_width is not None and image.width > self.max_width) or \
            (self.max_height is not None and image.height > self.max_height)

    def save(self, name, content, save=True):
        super().save(name, content, save=save)
        if hasattr(content, 'image'):
            if self.should_resize(content.image):
                try:
                    image = Image.open(self.file)
                    fp = io.BytesIO()
                    resized = image.resize(self.get_target_size(content.image))
                    resized.save(fp, format=image.format)
                    self.storage.delete(self.name)
                    self.save(name, fp, save=save)
                    fp.close()
                except Exception:
                    logger.error(
                        'ResizeImageFieldFile: Could not resize image',
                        exc_info=True,
                        extra={'filename': name, 'instance': self.instance}
                    )


class ResizeImageField(models.ImageField):
    attr_class = ResizeImageFieldFile

    def __init__(self, max_height=None, max_width=None, **kwargs):
        self.max_height, self.max_width = max_height, max_width
        super().__init__(**kwargs)


class TruncatedCharField(models.CharField):
    """Use for char fields that aren't super important, like in logs."""
    def to_python(self, value):
        value = super().to_python(value)
        if value and len(value) > self.max_length:
            logger.warning(
                'Value of TruncatedCharField exceeds max_length',
                extra={'model': getattr(self, 'model'), 'value': value}
            )
            return value[:self.max_length]
        return value
