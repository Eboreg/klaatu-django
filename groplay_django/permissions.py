from rest_framework.permissions import BasePermission


class UserObjectPermissions(BasePermission):
    """
    Usage: Implement the class method `has_permission(user, verb)` and/or the
    object method `has_object_permission(user, verb)` on the models.

    No need to check superuser status in those methods, since it's done
    here in has_permission().

    Also, if the object implements `has_object_permission()`, we assume the
    user is required to be authenticated, so no need to check that either.
    """
    VERB_MAPPING = {
        'GET': 'view',
        'POST': 'create',
        'PUT': 'change',
        'PATCH': 'change',
        'DELETE': 'delete',
    }

    def has_permission(self, request, view):
        if request.user.is_superuser or not hasattr(view, 'get_queryset'):
            return True
        try:
            queryset = view.get_queryset()
        except AssertionError:
            # This is _probably_ because the view does not use a queryset
            return True
        if (
            request.method in self.VERB_MAPPING and
            hasattr(queryset, 'model') and
            hasattr(queryset.model, 'has_permission')
        ):
            return queryset.model.has_permission(request.user, verb=self.VERB_MAPPING[request.method])
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        if obj is not None and request.method in self.VERB_MAPPING and hasattr(obj, 'has_object_permission'):
            if request.user.is_authenticated:
                return obj.has_object_permission(request.user, verb=self.VERB_MAPPING[request.method])
            return False
        return True
