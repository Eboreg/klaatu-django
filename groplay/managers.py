import logging

from django.db import models

logger = logging.getLogger(__name__)


class FailSafeManager(models.Manager):
    """Use when successful saving isn't crucial, like for log objects."""
    def create_or_log_error(self, **kwargs):
        try:
            return super().create(**kwargs)
        except Exception:
            logger.error('Could not create {} object'.format(self.model.__name__), exc_info=True)
            return None

    def create_quietly(self, **kwargs):
        try:
            return super().create(**kwargs)
        except Exception:
            return None
