import easy

from django.contrib import messages


def _set_is_active(modeladmin, request, queryset, value: bool):
    queryset.update(is_active=value)
    modeladmin.message_user(request, 'Updated %(count)d object(s).' % {'count': len(queryset)}, messages.SUCCESS)


@easy.short(desc='Mark selected %(verbose_name_plural)s as active')
def mark_as_active(modeladmin, request, queryset):
    _set_is_active(modeladmin, request, queryset, True)


@easy.short(desc='Mark selected %(verbose_name_plural)s as inactive')
def mark_as_inactive(modeladmin, request, queryset):
    _set_is_active(modeladmin, request, queryset, False)
