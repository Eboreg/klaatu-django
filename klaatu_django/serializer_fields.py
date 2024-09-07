from urllib.parse import urljoin

from rest_framework import serializers

from django.conf import settings


class FileURLField(serializers.URLField):
    def get_attribute(self, instance):
        try:
            return urljoin(settings.ROOT_URL, super().get_attribute(instance))  # type: ignore
        except ValueError:
            return None
