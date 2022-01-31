from typing import Optional, Union
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import DurationField, Model, QuerySet
from django.db.models.functions import Cast
from django.http import HttpRequest
from django.utils import timezone


def today():
    """Convenient, huh?"""
    return timezone.now().date()


def append_query_to_url(url: str, params: dict, conditional_params: Optional[dict] = None, safe: str = '') -> str:
    """
    Adds GET query from `params` to `url`, or appends it if there already is
    one.

    `conditional_params` will only be used if GET params with those keys are
    not already present in the original url or in `params`.

    Return the new url.
    """
    parts = urlsplit(url)
    conditional_params = conditional_params or {}
    qs = {
        **conditional_params,
        **parse_qs(parts.query),
        **params,
    }
    parts = parts._replace(query=urlencode(qs, doseq=True, safe=safe))
    return urlunsplit(parts)


def strip_url_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', parts.fragment))


class CastToDuration(Cast):
    VALID_UNITS = [
        {'name': 'microsecond', 'plural': 'microseconds', 'multiplier': 1},
        {'name': 'millisecond', 'plural': 'milliseconds', 'multiplier': 1000},
        {'name': 'second', 'plural': 'seconds', 'multiplier': 1_000_000},
        {'name': 'minute', 'plural': 'minutes', 'multiplier': 60_000_000},
        {'name': 'hour', 'plural': 'hours', 'multiplier': 3_600_000_000},
        {'name': 'day', 'plural': 'days', 'multiplier': 3_600_000_000 * 24},
        {'name': 'week', 'plural': 'weeks', 'multiplier': 3_600_000_000 * 24 * 7},
        {'name': 'month', 'plural': 'months', 'multiplier': 3_600_000_000 * 24 * 30},
        {'name': 'year', 'plural': 'years', 'multiplier': 3_600_000_000 * 24 * 365},
        {'name': 'decade', 'plural': 'decades', 'multiplier': 3_600_000_000 * 24 * 365 * 10},
        {'name': 'century', 'plural': 'centuries', 'multiplier': 3_600_000_000 * 24 * 365 * 100},
        {'name': 'millennium', 'plural': 'millennia', 'multiplier': 3_600_000_000 * 24 * 365 * 1000},
    ]

    def __init__(self, expression, unit: str):
        for valid_unit in self.VALID_UNITS:
            if unit in (valid_unit['name'], valid_unit['plural']):
                self.unit = valid_unit
                break
        if not hasattr(self, 'unit'):
            raise ValueError(f'"{unit}" is not a correct unit for CastToDuration.')
        super().__init__(expression, DurationField())

    def as_postgresql(self, compiler, connection, **extra_context):
        extra_context.update(unit=self.unit['name'])
        return self.as_sql(
            compiler,
            connection,
            template='(%(expressions)s || \' %(unit)s\')::%(db_type)s',
            **extra_context
        )

    def as_sqlite(self, compiler, connection, **extra_context):
        extra_context.update(multiplier=self.unit['multiplier'])
        template = '%(function)s(%(expressions)s * %(multiplier)d AS %(db_type)s)'
        return super().as_sqlite(compiler, connection, template=template, **extra_context)


def soupify(value: Union[str, bytes]) -> BeautifulSoup:
    """
    Background: BeautifulSoup wrongly guessed the encoding of API json
    responses as latin-1, which lead to bastardized strings and much agony
    until I finally found out why. Always run soup-creation through this!
    """
    if isinstance(value, bytes):
        return BeautifulSoup(value, 'html.parser', from_encoding='utf-8')
    return BeautifulSoup(value, 'html.parser')


class ObjectJSONEncoder(DjangoJSONEncoder):
    """Somewhat enhanced JSON encoder, for when you want that sort of thing."""
    def default(self, o):
        if isinstance(o, Model):
            return str(o.pk)
        if isinstance(o, QuerySet):
            return list(o)
        try:
            return super().default(o)
        except TypeError as ex:
            if hasattr(o, '__dict__'):
                return o.__dict__
            raise ex


def get_client_ip(request: HttpRequest) -> Optional[str]:
    """
    Very basic, but still arguably does a better job than `django-ipware`, as
    that one doesn't take port numbers into account.
    """
    meta_keys = (
        'HTTP_X_FORWARDED_FOR',
        'X_FORWARDED_FOR',
        'HTTP_CLIENT_IP',
        'HTTP_X_REAL_IP',
        'HTTP_X_FORWARDED',
        'HTTP_X_CLUSTER_CLIENT_IP',
        'HTTP_FORWARDED_FOR',
        'HTTP_FORWARDED',
        'HTTP_VIA',
        'REMOTE_ADDR',
    )
    value = None
    for key in meta_keys:
        if request.META.get(key):
            value = request.META[key].split(':')[0]
            if value:
                break
    return value
