from urllib.parse import urljoin

from django import template
from django.http.request import HttpRequest, QueryDict

register = template.Library()


@register.simple_tag
def join_query_params(request: HttpRequest, **kwargs) -> str:
    # Will coerce the new QueryDict to only contain one value for each key,
    # with priority to those in kwargs
    params = {k: v for k, v in request.GET.dict().items() if not isinstance(v, list)}
    params.update(kwargs)
    querydict = QueryDict(mutable=True)
    querydict.update(params)
    return request.path_info + '?' + querydict.urlencode()


@register.simple_tag(name='urljoin')
def urljoin_tag(base, url) -> str:
    return urljoin(base, url)
