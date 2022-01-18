from urllib.parse import urlsplit, urlunsplit

from django.db.models import DurationField
from django.db.models.functions import Cast
from django.http import QueryDict
from django.utils import timezone


def today():
    return timezone.now().date()


def append_url_query_params(url: str, params: dict) -> str:
    parts = urlsplit(url)
    query = QueryDict(parts.query, mutable=True)
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query.urlencode(), parts.fragment))


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
