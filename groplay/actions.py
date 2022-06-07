from django.contrib import admin, messages

"""
Admin actions, for use in ModelAdmin.actions lists.

NB: In order to use mark_as_active and mark_as_inactive, the model must have
an `is_active` boolean field.
"""


def _set_is_active(modeladmin, request, queryset, value: bool):
    queryset.update(is_active=value)
    modeladmin.message_user(request, 'Updated %(count)d object(s).' % {'count': len(queryset)}, messages.SUCCESS)


@admin.display(description='Mark selected %(verbose_name_plural)s as active')
def mark_as_active(modeladmin, request, queryset):
    _set_is_active(modeladmin, request, queryset, True)


@admin.display(description='Mark selected %(verbose_name_plural)s as inactive')
def mark_as_inactive(modeladmin, request, queryset):
    _set_is_active(modeladmin, request, queryset, False)
