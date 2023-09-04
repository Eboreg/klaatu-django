from abc import abstractmethod

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.utils import model_ngettext
from django.template.response import TemplateResponse

"""
Admin actions, for use in ModelAdmin.actions lists.

NB: In order to use mark_as_active and mark_as_inactive, the model must have
an `is_active` boolean field.
"""


def _set_is_active(modeladmin, request, queryset, value: bool):
    queryset.update(is_active=value)
    modeladmin.message_user(
        request,
        'Marked %d object(s) as %s.' % (len(queryset), 'active' if value else 'inactive'),
        messages.SUCCESS,
    )


@admin.action(description='Mark selected %(verbose_name_plural)s as active')
def mark_as_active(modeladmin, request, queryset):
    _set_is_active(modeladmin, request, queryset, True)


@admin.action(description='Mark selected %(verbose_name_plural)s as inactive')
def mark_as_inactive(modeladmin, request, queryset):
    _set_is_active(modeladmin, request, queryset, False)


class IntermediatePageAction:
    """
    Generalization of actions displaying intermediate pages. Its template
    must reside in some admin template directory, and contain this field:

    >>> <input type="hidden" name="action" value="{{ action }}" />

    Usage is analoguous to how View.as_view() is used in urlconfs:

    >>> actions = [ActionClass.as_function()]
    """
    description: str
    template_name: str

    def __init__(self, modeladmin, request, queryset):
        self.request = request
        self.modeladmin = modeladmin
        self.queryset = queryset

    @classmethod
    def as_function(cls):
        @admin.display(description=cls.description)  # type: ignore
        def action_func(modeladmin, request, queryset):
            return cls(modeladmin, request, queryset).dispatch()
        action_func.__name__ = cls.__name__
        return action_func

    def dispatch(self):
        if self.request.POST.get("post"):
            self.post()
            return None
        else:
            return self.get()

    def get(self):
        return TemplateResponse(
            self.request,
            [
                "admin/{}/{}/{}".format(
                    self.modeladmin.model._meta.app_label,
                    self.modeladmin.model._meta.model_name,
                    self.template_name,
                ),
                "admin/{}/{}".format(self.modeladmin.model._meta.app_label, self.template_name),
                "admin/{}".format(self.template_name),
            ],
            self.get_context_data(),
        )

    def get_context_data(self, **kwargs):
        return {
            **self.modeladmin.admin_site.each_context(self.request),
            "queryset": self.queryset,
            "media": self.modeladmin.media,
            "opts": self.modeladmin.model._meta,
            "title": self.description,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "objects_name": model_ngettext(self.queryset),
            "action": self.__class__.__name__,
            **kwargs,
        }

    @abstractmethod
    def post(self):
        ...
