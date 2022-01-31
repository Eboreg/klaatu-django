from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import set_rollback

from django.core.exceptions import PermissionDenied
from django.http import Http404


def exception_handler(exc, context):
    """
    Changes from original (in rest_framework.views):
      - Changed 'detail' key to 'error'
      - Pass on Http404 message to NotFound, rather than just calling it
    without context
    """
    if isinstance(exc, Http404):
        exc = exceptions.NotFound(str(exc))
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, exceptions.APIException):
        headers = {}
        auth_header = getattr(exc, 'auth_header', None)
        if auth_header is not None:
            headers['WWW-Authenticate'] = auth_header
        wait = getattr(exc, 'wait', None)
        if wait is not None:
            headers['Retry-After'] = '%d' % wait

        if isinstance(exc.detail, (list, dict)):
            data = exc.detail
        else:
            data = {'error': [exc.detail]}

        set_rollback()
        return Response(data, status=exc.status_code, headers=headers)

    return None
