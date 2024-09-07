import io
import logging
import pickle

from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models
from django.db.models import BinaryField, Case, F, FloatField, IntegerField, Q, Value as V, When
from django.db.models.expressions import Combinable, Expression
from django.db.models.fields.files import ImageFieldFile
from django.db.models.functions import Cast, Round

logger = logging.getLogger(__name__)


def TrueIf(*args, **kwargs) -> Expression:
    """Convenience method: 'if all the arguments are true, then true'."""
    return Case(When(Q(*args, **kwargs), then=V(True)), default=V(False))


def TrueIfAny(*args, **kwargs) -> Expression:
    """If _any_ of the arguments is true, then true."""
    conds = Q()
    for arg in args:
        conds |= Q(arg)
    for key, value in kwargs.items():
        conds |= Q(**{key: value})
    return Case(When(conds, then=V(True)), default=V(False))


def CorrectRound(field: str | Combinable) -> Expression:
    """
    Correctly rounds a numeric field to int.

    Formula: int(value + (int(value) % 2))
    So:
    CorrectRound(4.5) = int(4.5 + (4 % 2)) = int(4.5 + 0) = 4
    CorrectRound(3.5) = int(3.5 + (3 % 2)) = int(3.5 + 1) = 4
    """
    if isinstance(field, str):
        field = F(field)
    return Cast(
        field + (Cast(field, IntegerField()) % V(2)),
        # field + Mod(Cast(field, IntegerField()), V(2)),
        IntegerField()
    )


def PercentRounded(part: str, whole: str) -> Expression:
    """
    Given two numeric SQL fields, return a percentage as integer.
    """
    return Case(
        When(Q(**{whole: 0}), then=V(0)),
        default=Round(Cast(part, FloatField()) / F(whole) * 100, output_field=IntegerField())
    )


class ResizeImageFieldFile(ImageFieldFile):
    """Resize large images, silently report error on fail"""
    max_width: int | None
    max_height: int | None

    def __init__(self, instance, field, name):
        assert isinstance(field, ResizeImageField)
        self.max_height, self.max_width = field.max_height, field.max_width
        super().__init__(instance, field, name)

    def get_target_size(self, image: Image.Image) -> tuple[int, int]:
        width_divider = image.width / (self.max_width or image.width)
        height_divider = image.height / (self.max_height or image.height)
        divider = max([width_divider, height_divider])
        return int(image.width / divider), int(image.height / divider)

    def should_resize(self, image: Image.Image) -> bool:
        return (
            (self.max_width is not None and image.width > self.max_width) or
            (self.max_height is not None and image.height > self.max_height)
        )

    def save(self, name: str, content, save=True):
        super().save(name, content, save=save)
        content_image = getattr(content, "image", None)
        if content_image:
            if self.should_resize(content_image):
                try:
                    image = Image.open(self.file)
                    fp = io.BytesIO()
                    resized = image.resize(self.get_target_size(content_image))
                    resized.save(fp, format=image.format)
                    if self.name:
                        self.storage.delete(self.name)
                    self.save(name, File(fp), save=save)
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
        if value and self.max_length and len(value) > self.max_length:
            logger.warning(
                'Value of TruncatedCharField exceeds max_length',
                extra={'model': getattr(self, 'model', None), 'value': value}
            )
            return value[:self.max_length]
        return value


class TruncatedURLField(TruncatedCharField, models.URLField):
    ...


class PickleField(BinaryField):
    description = "Auto-pickled and unpickled object"

    def get_prep_value(self, value):
        return pickle.dumps(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return pickle.loads(value)

    def to_python(self, value):
        if isinstance(value, bytes):
            try:
                return pickle.loads(value)
            except Exception as e:
                raise ValidationError(f"{e.__class__} error in unpickling: {str(e)}") from e
        return value
