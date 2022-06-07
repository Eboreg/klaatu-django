from django.contrib import admin
from django.contrib.admin.options import BaseModelAdmin


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


class SetCreatedByAdmin(admin.ModelAdmin):
    # For use in admin pages for models with `created_by` fields
    def save_model(self, request, obj, form, change):
        if not change:
            try:
                obj.created_by = request.user
            except AttributeError:
                pass
        super().save_model(request, obj, form, change)


class SetCreatedByInlineAdmin(BaseModelAdmin):
    # Set `created_by` on inline objects in admin
    def save_formset(self, request, form, formset, change):
        formset.save()
        for obj in formset.new_objects:
            try:
                obj.created_by = request.user
                obj.save()
            except AttributeError:
                pass


class TabularManyToManyInline(admin.TabularInline):
    template = "admin/edit_inline/tabular_manytomany.html"
