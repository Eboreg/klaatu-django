from typing import Any, Callable, Mapping, Optional, Type

from django.conf import settings
from django.contrib import messages
from django.forms import Form
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import check_for_language
from django.views.generic.base import ContextMixin, View
from django.views.generic.detail import SingleObjectMixin, SingleObjectTemplateResponseMixin
from django.views.generic.edit import FormMixin, FormView, ModelFormMixin, ProcessFormView


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
    form_classes: Mapping[str, Type[Form]] = {}
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

    def get_forms(self, form_classes: Mapping[str, Type[Form]]) -> dict[str, Form]:
        return {
            key: klass(**self.get_form_kwargs_for(key))
            for key, klass in form_classes.items()
        }

    def get_form_errors(self, forms: dict[str, Form]) -> dict[str, list[str]]:
        errors: dict[str, list[str]] = {}
        for prefix, form in forms.items():
            for key, value in form.errors.items():
                if key == "__all__":
                    if "__all__" not in errors:
                        errors["__all__"] = []
                    errors["__all__"].extend(value)
                else:
                    errors[f"{prefix}-{key}"] = value
        return errors

    def clean_forms(self, forms: dict[str, Form]) -> bool:
        # TODO: Maybe make it more consistent with Django's clean*() methods
        # (don't return anything but update self.errors instead)
        return all([form.is_valid() for form in forms.values()])


class RedirectIfNotFoundMixin(SingleObjectMixin):
    """
    When detail view fails to get object, add a warning via messages and
    redirect to HTTP_REFERER (if exists) or `redirect_url` instead of Http404.

    Does not handle the actual redirect; for that, RedirectDetailView may be
    used, or the implementing class needs to do the check itself in its
    get(), post() or whichever method is applicable.
    """
    redirect_message: Optional[str] = None
    redirect_url: str
    request: HttpRequest

    def get_object(self, queryset=None):
        # If you override this in your implementing class and don't call
        # super().get_object(), make sure to add the warning
        try:
            return super().get_object(queryset)
        except Http404 as ex:
            messages.warning(self.request, self.redirect_message or str(ex))
            raise ex

    def get_redirect_url(self) -> str:
        if hasattr(self, "redirect_url"):
            return self.redirect_url
        if "HTTP_REFERER" in self.request.META:
            # Ugly hack so we don't redirect back to /login/?next=... or
            # whatever, which in turn would redirect us back here, and so on
            return self.request.META["HTTP_REFERER"].split("?")[0]
        return reverse("index")


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
        else:
            return self.forms_invalid(forms)

    def forms_valid(self, forms) -> HttpResponse:
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, forms) -> HttpResponse:
        return self.render_to_response(self.get_context_data(forms=forms))


class BaseRedirectIfNotFoundDetailView(RedirectIfNotFoundMixin, ContextMixin, View):
    # Analogous to Django's BaseDetailView.
    render_to_response: Callable

    def get(self, request: HttpRequest, *args, **kwargs):
        try:
            self.object = self.get_object()
            context = self.get_context_data(object=self.object)
            return self.render_to_response(context)
        except Http404:
            return redirect(self.get_redirect_url())


class BaseRedirectIfNotFoundUpdateView(RedirectIfNotFoundMixin, ModelFormMixin, ProcessFormView):
    # Analogous to Django's BaseUpdateView.
    def get(self, request: HttpRequest, *args, **kwargs):
        try:
            self.object = self.get_object()
            return super().get(request, *args, **kwargs)
        except Http404:
            return redirect(self.get_redirect_url())

    def post(self, request: HttpRequest, *args, **kwargs):
        try:
            self.object = self.get_object()
            return super().post(request, *args, **kwargs)
        except Http404:
            return redirect(self.get_redirect_url())


class RedirectDetailView(SingleObjectTemplateResponseMixin, BaseRedirectIfNotFoundDetailView):
    # Analogous to Django's DetailView.
    pass


class RedirectUpdateView(SingleObjectTemplateResponseMixin, BaseRedirectIfNotFoundUpdateView):
    # Analogous to Django's UpdateView.
    template_name_suffix = "_form"
