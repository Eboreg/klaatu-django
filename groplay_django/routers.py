from rest_framework.routers import DynamicRoute, Route, SimpleRouter


class SingletonRouter(SimpleRouter):
    """
    Router where the "root" route (without lookup args in the URL) is actually
    a detail view. It's up to the viewset to implement get_object() in a way
    that does not require any PK kwargs.
    """
    routes = [
        Route(
            url=r'^{prefix}{trailing_slash}$',
            mapping={
                'get': 'retrieve',
                'post': 'create',
                'put': 'update',
                'patch': 'partial_update',
                'delete': 'destroy',
            },
            name='{basename}-detail',
            detail=True,
            initkwargs={'suffix': 'Instance'}
        ),
        DynamicRoute(
            url=r'^{prefix}/{url_path}{trailing_slash}$',
            name='{basename}-{url_name}',
            detail=True,
            initkwargs={}
        ),
    ]
