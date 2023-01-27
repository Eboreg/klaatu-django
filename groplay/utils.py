import copy
import functools
import os
import re
import time
from datetime import date
from importlib import import_module
from math import ceil, floor, log10
from statistics import mean, median
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, SupportsFloat, TypeVar, Union
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.core.exceptions import ValidationError, ViewDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import validate_email
from django.db.models import DurationField, Model, QuerySet
from django.db.models.functions import Cast
from django.urls import URLPattern, URLResolver
from django.utils import timezone
from django.utils.translation import get_language, ngettext

_T = TypeVar("_T")


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
        return self.as_sql(  # type: ignore
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
        if isinstance(o, QuerySet):  # type: ignore
            return list(o)
        if isinstance(o, bytes):
            return "[Binary data]"
        try:
            return super().default(o)
        except TypeError as ex:
            if hasattr(o, '__dict__'):
                return o.__dict__
            raise ex


def get_client_ip(meta_dict: Dict[str, Any]) -> Optional[str]:
    """
    Very basic, but still arguably does a better job than `django-ipware`, as
    that one doesn't take port numbers into account.

    For use with HttpRequest, send `request.META`.
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
        if meta_dict.get(key):
            value = meta_dict[key].split(':')[0]
            if value:
                break
    return value


def relativedelta_rounded(dt1: timezone.datetime, dt2: timezone.datetime) -> relativedelta:
    """
    Rounds to the nearest "time unit", using perhaps arbitrary algorithms.
    """
    # First make sure both are naive OR aware:
    if timezone.is_naive(dt1) and not timezone.is_naive(dt2):
        dt1 = timezone.make_aware(dt1)
    elif timezone.is_naive(dt2) and not timezone.is_naive(dt1):
        dt2 = timezone.make_aware(dt2)
    delta = relativedelta(dt1, dt2)
    # >= 1 months or >= 25 days: return years + rounded months
    if delta.years or delta.months or delta.days >= 25:
        return relativedelta(years=delta.years, months=delta.months + round(delta.days / 30))
    # 7 - 24 days: return rounded weeks
    if delta.days >= 7:
        return relativedelta(weeks=round(delta.days / 7))
    # Dates are different: return that difference as number of days
    if dt1.day != dt2.day:
        return relativedelta(
            timezone.datetime(dt1.year, dt1.month, dt1.day),
            timezone.datetime(dt2.year, dt2.month, dt2.day)
        )
    # >= 1 hour: return rounded hours
    if delta.hours:
        return relativedelta(hours=delta.hours + round(delta.minutes / 60))
    # >= 1 minute: return minutes (not rounded!)
    if delta.minutes:
        return relativedelta(minutes=delta.minutes)
    # Don't bother with microseconds :P
    return delta


def timedelta_formatter(
    value: Union[timezone.timedelta, float, int],
    short_format: bool = False,
    rounded: bool = False
) -> str:
    # If value is float or int, we suppose it's number of seconds:
    if isinstance(value, (int, float)):
        seconds = int(value)
    else:
        seconds = int(value.total_seconds())
    hours = int(seconds / 3600)
    seconds -= (hours * 3600)
    minutes = int(seconds / 60)
    seconds -= (minutes * 60)
    if rounded:
        if minutes > 30:
            hours += 1
        if seconds > 30:
            minutes += 1
    if short_format:
        time_str = ""
        if hours:
            time_str += "{}h".format(hours)
        if minutes and (not rounded or not hours):
            time_str += "{}m".format(minutes)
        if seconds and (not rounded or (not hours and not minutes)):
            time_str += "{}s".format(seconds)
        return time_str or "0s"
    else:
        time_list = []
        if hours:
            time_list.append(ngettext("%(hours)d hour", "%(hours)d hours", hours) % {"hours": hours})
        if minutes and (not rounded or not hours):
            time_list.append(ngettext("%(min)d min", "%(min)d min", minutes) % {"min": minutes})
        if seconds and (not rounded or (not hours and not minutes)):
            time_list.append(ngettext("%(sec)d sec", "%(sec)d sec", seconds) % {"sec": seconds})
        return ", ".join(time_list)


def daterange(start_date: date, end_date: date) -> Iterator[date]:
    for n in range(int((end_date - start_date).days)):
        yield start_date + timezone.timedelta(days=n)


def percent_rounded(part: Union[int, float], whole: Union[int, float]) -> int:
    if not whole:
        return 0
    return round(part / whole * 100)


def extract_views_from_urlpatterns(
    urlpatterns=None,
    base="",
    namespace=None,
    app_name=None,
    app_names=None,
    only_parameterless=False,
    urlkwargs=[]
):
    views = {}
    if urlpatterns is None:
        root_urlconf = import_module(settings.ROOT_URLCONF)
        assert hasattr(root_urlconf, "urlpatterns")
        urlpatterns = getattr(root_urlconf, "urlpatterns", [])
        app_name = root_urlconf.__package__
    for p in urlpatterns:
        if isinstance(p, URLPattern) and (app_names is None or app_name in app_names):
            try:
                if only_parameterless and p.pattern.regex.groups > 0:
                    continue
                elif p.name and namespace:
                    view_name = f"{namespace}:{p.name}"
                elif p.name:
                    view_name = p.name
                else:
                    continue
                views[view_name] = {
                    "app_name": app_name,
                    "url": base + str(p.pattern),
                    "urlkwargs": urlkwargs + list(p.pattern.regex.groupindex),
                }
            except ViewDoesNotExist:
                continue
        elif isinstance(p, URLResolver):
            if p.app_name == "admin":
                # Hack: Never include admin urls
                continue
            if only_parameterless and p.pattern.regex.groups > 0:
                continue
            try:
                patterns = p.url_patterns
            except ImportError:
                continue
            if namespace and p.namespace:
                _namespace = f"{namespace}:{p.namespace}"
            else:
                _namespace = p.namespace or namespace
            if isinstance(p.urlconf_module, ModuleType):
                try:
                    _app_name = p.urlconf_module.app_name
                except AttributeError:
                    _app_name = p.urlconf_module.__package__
            else:
                _app_name = app_name
            views.update(extract_views_from_urlpatterns(
                urlpatterns=patterns,
                base=base + str(p.pattern),
                namespace=_namespace,
                app_name=_app_name,
                app_names=app_names,
                only_parameterless=only_parameterless,
                urlkwargs=urlkwargs + list(p.pattern.regex.groupindex)
            ))
    return {
        k: v
        for k, v in sorted(
            views.items(),
            key=lambda kv: kv[1]["app_name"] + kv[0]
        )
    }


def round_to_n(x: Union[int, float], n: int) -> SupportsFloat:
    """
    Rounds x to n significant digits, except if the result is a whole number
    it is cast to int
    """
    if x == 0:
        return x
    else:
        result = round(x, -int(floor(log10(abs(x)))) + (n - 1))
        return int(result) if not result % 1 else result


def rounded_percentage(part: Union[int, float], whole: Union[int, float]) -> SupportsFloat:
    """Percentage rounded to 3 significant digits"""
    return round_to_n((part / whole) * 100, 3) if whole != 0 else 0


def round_up_timedelta(td: timezone.timedelta) -> timezone.timedelta:
    """
    If td > 30 min, round up to nearest hour. Otherwise, to nearest 10
    minute mark. Could be extended for higher time units, but nevermind now.
    """
    td_minutes = td.total_seconds() / 60
    if td_minutes > 30:
        return timezone.timedelta(hours=ceil(td_minutes / 60))
    if td_minutes >= 10:
        return timezone.timedelta(minutes=int(td_minutes / 10) * 10 + 10)
    return timezone.timedelta(minutes=10)


def simple_pformat(obj: Any, indent: int = 4, current_depth: int = 0) -> str:
    """
    Pretty formatter that outputs stuff the way I want it, no more, no less
    """
    def format_value(v: Any) -> str:
        return f"'{v}'" if isinstance(v, str) else repr(v)

    def is_scalar(v: Any) -> bool:
        return isinstance(v, str) or not isinstance(v, Iterable)

    if isinstance(obj, dict):
        ret = "{"
        multiline = len(obj) > 1 or (len(obj) == 1 and not is_scalar(list(obj.values())[0]))
        if len(obj) > 0:
            if multiline:
                ret += "\n"
            for key, value in obj.items():
                if multiline:
                    ret += " " * (current_depth * indent + indent)
                ret += format_value(key) + ": "
                ret += simple_pformat(value, indent=indent, current_depth=current_depth + 1)
                if multiline:
                    ret += ",\n"
            if multiline:
                ret += " " * (current_depth * indent)
        ret += "}"
    elif isinstance(obj, (list, QuerySet)):  # type: ignore
        ret = "["
        multiline = len(obj) > 1 or (len(obj) == 1 and not is_scalar(obj[0]))
        if len(obj) > 0:
            if multiline:
                ret += "\n"
            for value in obj:
                if multiline:
                    ret += " " * (current_depth * indent + indent)
                ret += simple_pformat(value, indent=indent, current_depth=current_depth + 1)
                if multiline:
                    ret += ",\n"
            if multiline:
                ret += " " * (current_depth * indent)
        ret += "]"
    else:
        ret = format_value(obj)

    return ret


def int_to_string(value: Optional[int], language: str, nbsp: bool = False) -> str:
    # Format integer with correct thousand separators
    if value is None:
        return ""
    if language == "sv":
        # We probably should be checking for locale rather than language, but
        # whatever
        separator = " "
    else:
        separator = "."
    if separator == " " and nbsp:
        separator = "&nbsp;"
    # Neat line of code, huh? :)
    # 1. Use absolute value to get rid of minus sign
    # 2. Reverse str(value) in order to group characters from the end
    # 3. Split it by groups of 3 digits
    # 4. Remove empty values generated by re.split()
    # 5. Re-reverse the digits in each group & join them with separator string
    # 6. Re-reverse the order of the groups
    # 7. Add minus sign if value was negative
    return (
        ("-" if value < 0 else "") +
        separator.join([v[::-1] for v in re.split(r"(\d{3})", str(abs(value))[::-1]) if v][::-1])
    )


def circulate(lst: Union[list, tuple], rounds: int) -> list:
    """
    Shifts `lst` left `rounds` times. Good for e.g. circulating colours in
    a graph.
    """
    if isinstance(lst, tuple):
        lst = list(lst)
    if lst and rounds:
        for i in range(rounds):
            val = lst.pop(0)
            lst.append(val)
    return lst


def getitem_nullable(seq: Iterable[_T], idx: int, cond: Optional[Callable[[_T], bool]] = None) -> Optional[_T]:
    """
    If `seq` has an item at position `idx`, return that item. Otherwise return
    None. Similar to how QuerySet's first() & last() operate.

    With `cond` set, it first filters `seq` for items where this function
    evaluates as True, then tries to get item `idx` from the resulting list.

    Example:

    seq = [23, 43, 12, 56, 75, 1]
    second_even = getitem_nullable(seq, 1, lambda item: item % 2 == 0)
    # second_even == 56
    seq = [1, 2, 3, 5, 7]
    second_even = getitem_nullable(seq, 1, lambda item: item % 2 == 0)
    # second_even == None
    """
    try:
        if cond is not None:
            return [item for item in seq if cond(item)][idx]
        else:
            return list(seq)[idx]
    except IndexError:
        return None


def getitem0_nullable(seq: Iterable[_T], cond: Optional[Callable[[_T], bool]] = None) -> Optional[_T]:
    return getitem_nullable(seq, 0, cond)


def time_querysets(*querysets: QuerySet, iterations=10, quiet=False):
    """Purely a testing function to be used in the CLI."""
    last_percent = 0
    measurements = []

    for i in range(iterations):
        start_time = time.time()
        for queryset in querysets:
            list(copy.deepcopy(queryset))
        elapsed_time = time.time() - start_time
        measurements.append(elapsed_time)
        if quiet:
            percent = int((i + 1) / iterations * 100)
            if not percent % 10 and percent != last_percent:
                last_percent = percent
                output = f"{percent}%"
                if percent == 100:
                    print(output)
                else:
                    print(output, end=" ... ", flush=True)
        else:
            print(f"[{i + 1}/{iterations}: {elapsed_time}")

    print(f"Mean:   {mean(measurements)}")
    print(f"Median: {median(measurements)}")


class LockException(Exception):
    ...


def lock(lockfile: str):
    """Primitive mechanism to avoid concurrent execution of a function."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if os.path.exists(lockfile):
                raise LockException(f"Could not acquire lockfile: {lockfile}")

            else:
                with open(lockfile, "w") as f:
                    f.write("LOCK")

                result = func(*args, **kwargs)

                # Multiple attempts just to be super sure I guess?
                remote_attempts = 0
                while os.path.exists(lockfile) and remote_attempts < 10:
                    os.remove(lockfile)
                    remote_attempts += 1

                return result
        return wrapper
    return decorator


class Lock:
    """Does the same as `lock`, but as a context manager."""
    def __init__(self, lockfile: str):
        self.lockfile = lockfile

    def __enter__(self):
        if os.path.exists(self.lockfile):
            raise LockException(f"Could not acquire lockfile: {self.lockfile}")
        with open(self.lockfile, "w") as f:
            f.write("LOCKED")

    def __exit__(self, *args, **kwargs):
        remote_attempts = 0
        while os.path.exists(self.lockfile) and remote_attempts < 10:
            os.remove(self.lockfile)
            remote_attempts += 1


def index_of_first(sequence: Sequence[_T], pred: Callable[[_T], bool]) -> int:
    """
    Tries to return the index of the first item in `sequence` for which the
    function `pred` returns True. If no such item is found, return -1.
    """
    try:
        return sequence.index(next(filter(pred, sequence)))
    except StopIteration:
        return -1


def group_by(sequence: Sequence[_T], pred: Callable[[_T], Any]) -> Dict[Any, List[_T]]:
    """
    Groups `sequence` by the result of `pred` on each item. Returns dict with
    those results as keys and sublists of `sequence` as values.
    """
    result = {}
    for item in sequence:
        key = pred(item)
        if key not in result:
            result[key] = [item]
        else:
            result[key].append(item)
    return result


def is_truthy(value: Any) -> bool:
    """
    Basically does `bool(value)`, except it also returns False for string
    values "false", "no", and "0" (case insensitive).
    """
    if isinstance(value, str) and value.lower() in ("false", "no", "0"):
        return False
    return bool(value)


def is_valid_email(value: Any) -> bool:
    try:
        validate_email(value)
    except (ValidationError, TypeError):
        return False
    return True


def to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def capitalize(string: Optional[str], language: Optional[str] = None) -> str:
    """
    Language-dependent word capitalization. For English, it capitalizes every
    word except some hard-coded exceptions (the first and last word are always
    capitalized, however). For all other languages, only the first word.

    Side effect: Will replace multiple consecutive spaces with only one space.

    @param language Optional, will use current session's language if not set.
    """
    language = language or get_language()

    if string is None:
        return ""

    if language == "en":
        non_capped = ['a', 'an', 'and', 'but', 'for', 'from', 'if', 'nor', 'of', 'or', 'so', 'the']
        words = string.split(" ")
        for idx, word in enumerate(words):
            if word and (idx == 0 or idx == len(words) - 1 or re.sub(r"\W", "", word).lower() not in non_capped):
                words[idx] = word[0].upper() + word[1:]
        return " ".join(words)
    else:
        return string.capitalize()
