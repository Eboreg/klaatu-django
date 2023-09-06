import copy
import os
import re
import time
from abc import ABCMeta
from datetime import datetime, timedelta
from importlib import import_module
from os.path import basename, splitext
from statistics import mean, median
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, Iterable, TypeVar

from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from rest_framework.serializers import SerializerMetaclass

from django.conf import settings
from django.core.exceptions import ValidationError, ViewDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import validate_email
from django.db.models import DurationField, Model, QuerySet
from django.db.models.functions import Cast
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import URLPattern, URLResolver
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import get_language, gettext, ngettext

if TYPE_CHECKING:
    from django.utils.functional import _StrPromise  # type: ignore

_T = TypeVar("_T")


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


class FailSafeJSONEncoder(DjangoJSONEncoder):
    """
    A JSON encoder that will not fail, but its results cannot be used to
    reliably restore the original data.
    """
    def default(self, o):
        try:
            return super().default(o)
        except TypeError as e:
            return str(e)


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


class LockException(Exception):
    ...


class ObjectJSONEncoder(DjangoJSONEncoder):
    """
    Somewhat enhanced JSON encoder, for when you want that sort of thing.
    Represents Django models with their string representations and binary
    values are redacted, so it cannot be used to reliably load a previous
    dump.
    """
    def default(self, o):
        if isinstance(o, Model):
            return str(o.pk)
        if isinstance(o, QuerySet):  # type: ignore
            return list(o)
        if isinstance(o, bytes):
            return "[Binary data]"
        if isinstance(o, set):
            o = list(o)
        try:
            return super().default(o)
        except TypeError as ex:
            if hasattr(o, '__dict__'):
                return o.__dict__
            raise ex


class SerializerABCMeta(SerializerMetaclass, ABCMeta):
    """
    To be used with "abstract" base serializer classes. Usage:

    from abc import ABC
    from rest_framework.serializers import Serializer

    class MyBaseSerializer(Serializer, ABC, metaclass=SerializerABCMeta):
        ...
    """


def capitalize(string: "str | _StrPromise | None", language: str | None = None) -> str:
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
    return string.capitalize()


def extract_views_from_urlpatterns(
    urlpatterns=None,
    base="",
    namespace=None,
    app_name=None,
    app_names=None,
    only_parameterless=False,
    urlkwargs=None,
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
                if p.name and namespace:
                    view_name = f"{namespace}:{p.name}"
                elif p.name:
                    view_name = p.name
                else:
                    continue
                views[view_name] = {
                    "app_name": app_name,
                    "url": base + str(p.pattern),
                    "urlkwargs": (urlkwargs or []) + list(p.pattern.regex.groupindex),
                }
            except ViewDoesNotExist:
                continue
        elif isinstance(p, URLResolver):
            # Hack: Never include admin urls
            if p.app_name == "admin" or (only_parameterless and p.pattern.regex.groups > 0):
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
            views.update(
                extract_views_from_urlpatterns(
                    urlpatterns=patterns,
                    base=base + str(p.pattern),
                    namespace=_namespace,
                    app_name=_app_name,
                    app_names=app_names,
                    only_parameterless=only_parameterless,
                    urlkwargs=(urlkwargs or []) + list(p.pattern.regex.groupindex),
                )
            )
    return dict(sorted(views.items(), key=lambda kv: kv[1]['app_name'] + kv[0]))


def get_client_ip(meta_dict: Dict[str, Any]) -> str | None:
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
        meta_value = meta_dict.get(key, None)
        if isinstance(meta_value, str):
            value = meta_value.split(':')[0]
            if value:
                break
    return value


def is_url_name(value: str) -> bool:
    """
    Really just a guess, based on a somewhat consistent naming of Django URLs.
    """
    return bool(re.match(r"^[a-zA-Z0-9_\-:]+$", value))


def is_valid_email(value: Any) -> bool:
    try:
        validate_email(value)
    except (ValidationError, TypeError):
        return False
    return True


def natural_and_list(items: Iterable, enclose_items_in_tag="") -> str:
    return natural_list(items, enclose_items_in_tag=enclose_items_in_tag)


def natural_list(items: Iterable, or_separated=False, enclose_items_in_tag="") -> str:
    """
    Turns `items` into a natural-language string. Will be "or"-separated if
    `or_separated == True`, else "and"-separated. Of course, the English
    original strings use the Oxford comma.

    Example:
    In [1]: natural_list(
       ...:     ["foo", "bar", "baz"],
       ...:     or_separated=True,
       ...:     enclose_items_in_tag="em"
       ...: )
    Out[1]: '<em>foo</em>, <em>bar</em>, or <em>baz</em>'
    """
    def enclose(item):
        if enclose_items_in_tag:
            return "<%s>%s</%s>" % (enclose_items_in_tag, item, enclose_items_in_tag)
        return str(item)

    item_list = list(items)
    if len(item_list) == 0:
        return ""
    if len(item_list) == 1:
        return enclose(item_list[0])
    if len(item_list) == 2:
        return "%s %s %s" % (
            enclose(item_list[0]),
            gettext("or") if or_separated else gettext("and"),
            enclose(item_list[1]),
        )
    vars = {"list": ", ".join([enclose(i) for i in item_list[:-1]]), "last_item": enclose(item_list[-1])}
    if or_separated:
        # Translators: %(list)s is a comma-separated list of >= 2 items.
        return gettext("%(list)s, or %(last_item)s") % vars
    # Translators: %(list)s is a comma-separated list of >= 2 items.
    return gettext("%(list)s, and %(last_item)s") % vars


def natural_or_list(items: Iterable, enclose_items_in_tag="") -> str:
    return natural_list(items, or_separated=True, enclose_items_in_tag=enclose_items_in_tag)


def relativedelta_rounded(dt1: datetime, dt2: datetime) -> relativedelta:
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
            datetime(dt1.year, dt1.month, dt1.day),
            datetime(dt2.year, dt2.month, dt2.day)
        )
    # >= 1 hour: return rounded hours
    if delta.hours:
        return relativedelta(hours=delta.hours + round(delta.minutes / 60))
    # >= 1 minute: return minutes (not rounded!)
    if delta.minutes:
        return relativedelta(minutes=delta.minutes)
    # Don't bother with microseconds :P
    return delta


def render_modal(
    template_name: str,
    request: HttpRequest | None = None,
    modal_id="",
    classes="",
    required_params="",
    optional_params="",
    footer=True,
    large=False,
    scrollable=False,
    center=False,
    context: Dict[str, Any] | None = None,
):
    """
    Gets a Bootstrap modal from the template file `template_name`, renders it
    with context from the parameters, and returns the result. The template
    file will preferably extend groplay/modals/base.html.

    `required_params` and `optional_params` are there to tell the JS function
    openModalOnLoad() which GET params to look for. The required ones will
    be injected as `data-required-params` on the .modal element in base.html,
    the optional ones as `data-optional-params`. All those parameters will be
    stripped from the URL when openModalOnLoad() is finished. The only
    difference between the two kinds is that without the required parameters,
    openModalOnLoad() will refuse to open the modal.
    """
    param_list = _get_param_list(required_params, optional_params)

    if not modal_id:
        modal_id = splitext(basename(template_name))[0].replace("_", "-") + "-modal"

    context = context or {}
    context["modal"] = {
        "required_params": required_params,
        "optional_params": optional_params,
        "all_params": param_list,
        "id": modal_id,
        "classes": classes,
        "footer": footer,
        "large": large,
        "scrollable": scrollable,
        "center": center,
    }
    return mark_safe(render_to_string(template_name=template_name, context=context, request=request))


def simple_pformat(obj: Any, indent: int = 4, current_depth: int = 0) -> str:
    """
    Pretty formatter that outputs stuff the way I want it, no more, no less
    """
    def format_value(v: Any) -> str:
        return f"'{v}'" if isinstance(v, str) else repr(v)

    def is_scalar(v: Any) -> bool:
        return isinstance(v, str) or not isinstance(v, Iterable)

    def format_dict(obj: dict) -> str:
        ret = "{"
        if len(obj) > 0:
            multiline = len(obj) > 1 or (len(obj) == 1 and not is_scalar(list(obj.values())[0]))
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
        return ret

    def format_list_or_queryset(obj: list | QuerySet) -> str:
        ret = "["
        if len(obj) > 0:
            multiline = len(obj) > 1 or (len(obj) == 1 and not is_scalar(obj[0]))
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
        return ret

    if isinstance(obj, dict):
        return format_dict(obj)
    if isinstance(obj, (list, QuerySet)):
        return format_list_or_queryset(obj)
    return format_value(obj)


def soupify(value: str | bytes) -> BeautifulSoup:
    """
    Background: BeautifulSoup wrongly guessed the encoding of API json
    responses as latin-1, which lead to bastardized strings and much agony
    until I finally found out why. Always run soup-creation through this!
    """
    if isinstance(value, bytes):
        return BeautifulSoup(value, 'html.parser', from_encoding='utf-8')
    return BeautifulSoup(value, 'html.parser')


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


def timedelta_formatter(
    value: timedelta | float | int,
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
    time_list = []
    if hours:
        time_list.append(ngettext("%(hours)d hour", "%(hours)d hours", hours) % {"hours": hours})
    if minutes and (not rounded or not hours):
        time_list.append(ngettext("%(min)d min", "%(min)d min", minutes) % {"min": minutes})
    if seconds and (not rounded or (not hours and not minutes)):
        time_list.append(ngettext("%(sec)d sec", "%(sec)d sec", seconds) % {"sec": seconds})
    return ", ".join(time_list)


def _get_param_list(required_params: str = "", optional_params: str = "") -> list[str]:
    required_params = required_params.strip()
    optional_params = optional_params.strip()
    return (
        (required_params.split(" ") if required_params else []) +
        (optional_params.split(" ") if optional_params else [])
    )
