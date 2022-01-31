from typing import Any

from django.conf import settings
from django.utils.translation import check_for_language


class LanguageMixin:
    """
    To be used with Django REST Framework views. Sets 'language' in the
    context of the serializer (which, preferably, should inherit from
    `groplay.serializer_mixins.LanguageMixin`).
    """
    request: Any

    def get_language(self) -> str:
        """
        Priority:

        1. `language` GET param
        2. Authenticated user's language
        3. `settings.LANGUAGE_CODE_SESSION_KEY` session variable
        4. Default
        """
        assert hasattr(self, 'request')
        if hasattr(self.request, 'query_params'):
            language = self.request.query_params.get('language', None)
            if language and check_for_language(language):
                return language
        if hasattr(self.request, 'user') and hasattr(self.request.user, 'language'):
            return self.request.user.language
        if hasattr(self.request, 'session') and \
                hasattr(settings, 'LANGUAGE_CODE_SESSION_KEY') and \
                settings.LANGUAGE_CODE_SESSION_KEY in self.request.session:
            return self.request.session[settings.LANGUAGE_CODE_SESSION_KEY]
        return settings.LANGUAGE_CODE

    def get_serializer_context(self):
        context = super().get_serializer_context()  # type: ignore
        context['language'] = self.get_language()
        return context
