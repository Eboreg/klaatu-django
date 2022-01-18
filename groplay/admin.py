from django.contrib import admin


class BooleanListFilter(admin.SimpleListFilter):
    def lookups(self, request, model_admin):
        return [('1', 'Yes'), ('0', 'No')]

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(**{self.parameter_name: True})
        if self.value() == '0':
            return queryset.filter(**{self.parameter_name: False})


class NoDeleteActionMixin:
    def get_actions(self, request):
        actions = super().get_actions(request)  # type: ignore
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class CreatedByMixin:
    def save_formset(self, request, form, formset, change):
        # As a bonus, let's also set created_by on any applicable, newly
        # created inline objects.
        for inline_form in formset.forms:
            if inline_form.instance.pk is None and hasattr(inline_form.instance, 'created_by'):
                inline_form.instance.created_by = request.user
        return super().save_formset(request, form, formset, change)  # type: ignore

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)  # type: ignore

    def get_readonly_fields(self, request, obj=None):
        return ('created', 'created_by', *super().get_readonly_fields(request, obj=obj))  # type: ignore
