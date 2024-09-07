from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AdminBasicAuthentication(BasicAuthentication):
    """Extending the basic auth to only allow superuser accounts"""
    def authenticate_credentials(self, userid, password, request=None):
        user, _ = super().authenticate_credentials(userid, password, request=request)
        if not getattr(user, "is_superuser", False):
            raise AuthenticationFailed('User is not superuser.')
        return (user, None)
