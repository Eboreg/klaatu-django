from typing import Optional

from django.contrib import admin
from django.contrib.admin.options import BaseModelAdmin
from django.contrib.admin.sites import AdminSite
from django.contrib.admin.utils import quote
from django.db.models import Model, QuerySet
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.urls import reverse
from django.utils.html import format_html


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


class RelatedLinkMixin:
    admin_site: AdminSite

    def get_related_changeform_link(self, related_obj: Optional[Model], display_attr: Optional[str] = None):
        """
        If `related_obj` is a model instance, and its model is registered with
        the AdminSite, return a link to the changeform for this instance.
        Otherwise, just return `related_obj` as-is.

        If `display_attr` is set, `related_obj` is displayed using this
        attribute on the model. Otherwise by the model's __str__().

        Usage:

        list_display = (..., "user_link", ...)

        @admin.display(description="user", ordering="user__username")
        def user_link(self, obj):
            return self.get_related_changeform_link(obj.user, "username")
        """
        if (
            isinstance(related_obj, Model) and
            self.admin_site.is_registered(related_obj._meta.model) and
            related_obj._meta.pk
        ):
            pk = getattr(related_obj, related_obj._meta.pk.attname)
            return format_html(
                '<a href="{}">{}</a>',
                reverse(
                    "admin:%s_%s_change" % (related_obj._meta.app_label, related_obj._meta.model_name),
                    args=(quote(pk),),
                    current_app=self.admin_site.name
                ),
                getattr(related_obj, display_attr) if display_attr else related_obj
            )
        return related_obj

    def get_related_changeform_link_list(self, related_queryset: QuerySet, display_attr: Optional[str] = None):
        """
        Returns links to changeform for each item in `related_queryset`,
        separated by '<br />'. If queryset's model is not registered with the
        AdminSite, returns the same list but without links.

        If `display_attr` is set, items are displayed using this attribute
        on the model instances. Otherwise by the model's __str__().

        Usage:

        list_display = (..., "user_link_list", ...)

        @admin.display(description="users", ordering="users__username")
        def user_link_list(self, obj):
            return self.get_related_changeform_link_list(
                obj.users.all(),
                "username"
            )
        """
        if self.admin_site.is_registered(related_queryset.model):
            opts = related_queryset.model._meta
            return format_html("<br />".join(
                [
                    '<a href="%s">%s</a>' % (
                        reverse(
                            "admin:%s_%s_change" % (opts.app_label, opts.model_name),
                            args=(quote(getattr(obj, opts.pk.attname)),),
                            current_app=self.admin_site.name
                        ),
                        getattr(obj, display_attr) if display_attr else obj
                    )
                    for obj in related_queryset
                ]
            ))
        return format_html("<br />".join([
            str(getattr(obj, display_attr)) if display_attr else str(obj)
            for obj in related_queryset
        ]))

    def get_related_changelist_link(
        self,
        obj: Optional[Model],
        related_name: str,
        verbose_name: Optional[str] = None,
        verbose_name_plural: Optional[str] = None
    ):
        """
        `related_name` should be the name of a many-to-many or many-to-one
        (reverse foreign key relationship) field on `obj`. If the related
        model is registered with the AdminSite, return a link to that model's
        changelist, filtered for those instances that are related to `obj`.

        Link text will be "[number of instances] [verbose_name[_plural]]",
        where `verbose_name[_plural]` is either set in the method arguments or
        collected from the related model's meta attributes. The usage of the
        "_plural" suffix is of course dependent upon the number of related
        objects found.

        Usage:

        list_display = (..., "user_list_link", ...)

        @admin.display(description="users")
        def user_list_link(self, obj):
            return self.get_related_changelist_link(obj, "users")

        """
        if obj is None or obj._meta.pk is None:
            return None

        related_field = obj._meta.get_field(related_name)

        if isinstance(related_field, ForeignObjectRel) and self.admin_site.is_registered(related_field.related_model):
            related_model = related_field.related_model
            opts = related_model._meta
            verbose_name = verbose_name or related_model._meta.verbose_name
            verbose_name_plural = verbose_name_plural or related_model._meta.verbose_name_plural
            obj_count = getattr(obj, related_name).count()

            return format_html(
                '<a href="{}?{}__exact={}">{} {}</a>',
                reverse(
                    "admin:%s_%s_changelist" % (opts.app_label, opts.model_name),
                    current_app=self.admin_site.name
                ),
                related_field.field.get_attname(),
                getattr(obj, obj._meta.pk.attname),
                obj_count,
                verbose_name if obj_count == 1 else verbose_name_plural
            )


class ExtendedModelAdmin(RelatedLinkMixin, admin.ModelAdmin):
    """Meant to collect all kinds of useful extra functionality."""
    pass


class ExtendedTabularInline(RelatedLinkMixin, admin.TabularInline):
    pass


class ExtendedStackedInline(RelatedLinkMixin, admin.StackedInline):
    pass
