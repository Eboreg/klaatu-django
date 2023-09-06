from typing import Any, Mapping

from django.conf import settings
from django.contrib import messages
from django.forms import Form
from django.forms.utils import ErrorList
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.translation import check_for_language
from django.views.generic.base import View
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.views.generic.edit import FormMixin, FormView, UpdateView


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
        LANGUAGE_CODE_SESSION_KEY = getattr(settings, "LANGUAGE_CODE_SESSION_KEY", None)

        if hasattr(self.request, 'query_params'):
            language = self.request.query_params.get('language', None)
            if language and check_for_language(language):
                return language
        if hasattr(self.request, 'user') and hasattr(self.request.user, 'language'):
            return self.request.user.language
        if (
            hasattr(self.request, 'session') and
            LANGUAGE_CODE_SESSION_KEY and
            LANGUAGE_CODE_SESSION_KEY in self.request.session
        ):
            return self.request.session[LANGUAGE_CODE_SESSION_KEY]
        return settings.LANGUAGE_CODE

    def get_serializer_context(self):
        context = super().get_serializer_context()  # type: ignore
        context['language'] = self.get_language()
        return context


class MultipleFormsMixin(FormMixin):
    """
    Inspired by extra_views and https://gist.github.com/michelts/1029336

    initial_data format: {form_prefix: {key: value, ...}, ...}
    form_classes format: {form_prefix: form_class, ...}
    """
    form_classes: Mapping[str, type[Form]] = {}
    request: HttpRequest

    def get_form_classes(self):
        return self.form_classes

    def get_form(self, form_class=None):
        # Otherwise FormMixin.get_form() will mess with us
        return None

    def get_initial_for(self, key: str) -> dict[str, Any]:
        return {}

    def get_form_kwargs_for(self, key: str) -> dict[str, Any]:
        kwargs = {
            "initial": {
                **self.get_initial().get(key, {}),
                **self.get_initial_for(key)
            },
            "prefix": key,
        }
        if self.request.method in ("POST", "PUT"):
            kwargs.update(
                data=self.request.POST,
                files=self.request.FILES,
            )
        return kwargs

    def get_forms(self, form_classes: Mapping[str, type[Form]]) -> dict[str, Form]:
        return {
            key: klass(**self.get_form_kwargs_for(key))
            for key, klass in form_classes.items()
        }

    def get_form_errors(self, forms: dict[str, Form]) -> dict[str, ErrorList]:
        errors: dict[str, ErrorList] = {}
        for prefix, form in forms.items():
            for key, value in form.errors.items():
                if key == "__all__":
                    if "__all__" not in errors:
                        errors["__all__"] = ErrorList()
                    errors["__all__"].extend(value)
                else:
                    errors[f"{prefix}-{key}"] = value
        return errors

    def clean_forms(self, forms: dict[str, Form]) -> bool:
        # TODO: Maybe make it more consistent with Django's clean*() methods
        # (don't return anything but update self.errors instead)
        return all(form.is_valid() for form in forms.values())


class MultipleFormsView(MultipleFormsMixin, FormView):
    """
    Inspired by extra_views and https://gist.github.com/michelts/1029336
    """
    def get(self, request, *args, **kwargs):
        form_classes = self.get_form_classes()
        forms = self.get_forms(form_classes)
        return self.render_to_response(self.get_context_data(forms=forms, **kwargs))

    def post(self, request, *args, **kwargs):
        form_classes = self.get_form_classes()
        forms = self.get_forms(form_classes)
        if self.clean_forms(forms):
            return self.forms_valid(forms)
        return self.forms_invalid(forms)

    def forms_valid(self, forms) -> HttpResponse:
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, forms) -> HttpResponse:
        return self.render_to_response(self.get_context_data(forms=forms))


class RedirectIfNotFoundMixin(SingleObjectMixin):
    """
    Convenience mixin for redirecting to a chosen URL when an object is not
    found, with an optional error message.
    """
    fallback_to_referer = True
    redirect_message: str | None = None
    redirect_url: str | None = None
    request: HttpRequest

    def get_redirect_message(self) -> str | None:
        return getattr(self, "redirect_message", None)

    def get_redirect_url(self) -> str:
        if self.redirect_url:
            return self.redirect_url
        if self.fallback_to_referer and "referer" in self.request.headers:
            # Ugly hack so we don't redirect back to /login/?next=... or
            # whatever, which in turn would redirect us back here, and so on
            return self.request.headers["referer"].split("?")[0]
        # Last resort:
        raise Http404

    def redirect_with_message(self, exception: Http404 | None = None):
        message = self.get_redirect_message()
        if not message and exception is not None:
            message = str(exception)
        if message:
            messages.error(self.request, message)
        return redirect(self.get_redirect_url())


class BaseRedirectIfNotFoundView(RedirectIfNotFoundMixin, View):
    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404 as e:
            return self.redirect_with_message(e)


class RedirectDetailView(BaseRedirectIfNotFoundView, DetailView):
    pass


class RedirectUpdateView(BaseRedirectIfNotFoundView, UpdateView):
    pass
