import re
from datetime import date, datetime
from os.path import basename, splitext
from typing import Any, List, Optional, Union
from urllib.parse import urljoin

from django import template
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import NaturalTimeFormatter
from django.http.request import HttpRequest, QueryDict
from django.template.defaultfilters import stringfilter
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.timesince import timesince, timeuntil
from django.utils.translation import gettext_lazy, ngettext_lazy, override

from groplay.utils import relativedelta_rounded, timedelta_formatter

register = template.Library()


class NaturalTimeShortFormatterMeta(type):
    def __new__(cls, name, bases, dct):
        klass = super().__new__(cls, name, bases, dct)
        time_strings = getattr(klass, "time_strings", {})
        time_strings.update({
            # The 'past' ones are identical to the originals, but I'm
            # including them because the default Swedish translation is wrong
            # The stubs are also wrong in assuming we cannot pass a string as
            # argument instead of an int:
            # https://docs.djangoproject.com/en/2.2/topics/i18n/translation/#lazy-translations-and-plural
            'past-day': gettext_lazy('%(delta)s ago'),
            'past-hour': ngettext_lazy('an hour ago', '%(count)s hours ago', 'count'),
            'past-minute': ngettext_lazy('a minute ago', '%(count)s minutes ago', 'count'),
            'past-second': ngettext_lazy('a second ago', '%(count)s seconds ago', 'count'),
            'future-second': ngettext_lazy('in one second', 'in %(count)s seconds', 'count'),
            'future-minute': ngettext_lazy('in one minute', 'in %(count)s minutes', 'count'),
            'future-hour': ngettext_lazy('in one hour', 'in %(count)s hours', 'count'),
            'future-day': gettext_lazy('in %(delta)s'),
            "yesterday": gettext_lazy("yesterday"),
            "tomorrow": gettext_lazy("tomorrow"),
        })
        setattr(klass, "time_strings", time_strings)
        return klass


class NaturalTimeShortFormatter(NaturalTimeFormatter, metaclass=NaturalTimeShortFormatterMeta):
    """
    Ugly hack to only return the first part of the string when the timedelta
    >= 1 day (NaturalTimeFormatter returns "1 month, 3 days" etc, we only
    want "1 month" here)
    """
    @classmethod
    def string_for(cls, then):
        if not isinstance(then, date):
            return then
        if not isinstance(then, datetime):
            then = datetime.combine(then, datetime.min.time())

        now = datetime.now(timezone.utc if timezone.is_aware(then) else None)
        # Make it as round as we want it:
        relative_delta = relativedelta_rounded(now, then)
        now = then + relative_delta

        if then < now:
            if abs(relative_delta.days) == 1:
                return cls.time_strings["yesterday"]
            delta = now - then
            if delta.days != 0:
                delta_str = timesince(then, now, time_strings=cls.past_substrings)
                return cls.time_strings["past-day"] % {
                    "delta": delta_str.split(", ")[0]
                }
        else:
            if abs(relative_delta.days) == 1:
                return cls.time_strings["tomorrow"]
            delta = then - now
            if delta.days != 0:
                delta_str = timeuntil(then, now, time_strings=cls.future_substrings)
                return cls.time_strings["future-day"] % {
                    "delta": delta_str.split(", ")[0]
                }
        return super().string_for(then)


### TAGS ##################################

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


@register.simple_tag(takes_context=True)
def modal(
    context: template.RequestContext,
    template_name: str,
    modal_id: str = "",
    classes: str = "",
    required_params: str = "",
    optional_params: str = "",
    footer: bool = True,
    large: bool = False,
    scrollable=False,
    **kwargs
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
    required_params = required_params.strip()
    optional_params = optional_params.strip()

    if not modal_id:
        modal_id = splitext(basename(template_name))[0].replace("_", "-") + "-modal"

    context["modal"] = {
        "required_params": required_params.split(" ") if required_params else [],
        "optional_params": optional_params.split(" ") if optional_params else [],
        "id": modal_id,
        "classes": classes,
        "footer": footer,
        "large": large,
        "scrollable": scrollable,
    }
    context.update(kwargs)
    return mark_safe(render_to_string(template_name, context.flatten()))


@register.inclusion_tag("groplay/modals/dynamic.html")
def dynamic_modal(
    modal_id: str,
    url: str = "",
    classes: str = "",
    required_params: str = "",
    optional_params: str = "",
    large=False,
    always_load=False,
    scrollable=False,
):
    """
    Includes the Bootstrap modal "skeleton" from groplay/modals/dynamic.html
    and renders it in a similar way to `modal()`, except it also sets
    `data-content-url` on the .modal element. On modal show event, the JS
    function loadDynamicContent() will load the contents from this URL into
    the modal.

    The template rendered by this URL will preferably extend
    groplay/modals/dynamic_content.html.
    """
    required_params = required_params.strip()
    optional_params = optional_params.strip()

    url = url.strip()
    if url and not url.startswith("/"):
        try:
            url = reverse(url)
        except Exception:
            pass

    return {
        "modal": {
            "id": modal_id.strip(),
            "url": url,
            "classes": classes.strip(),
            "required_params": required_params.split(" ") if required_params else [],
            "optional_params": optional_params.split(" ") if optional_params else [],
            "large": large,
            "always_load": always_load,
            "scrollable": scrollable,
        },
    }


@register.inclusion_tag("groplay/preloader.html")
def preloader(id: Optional[str] = None, fixed=False, show=False, small=False):
    """
    Inserts a .preloader element, which will then be shown and hidden by JS.
    Extend groplay/preloader.html to customize it.

    @param fixed Preloader should have position: fixed (default: absolute)
    @param show Show preloader on load
    @param small Shrink font & image sizes to 75%
    `size` should be a percentage string, which probably should not be less
    than "75%".
    """
    return {
        "preloader": {
            "id": id,
            "fixed": fixed,
            "show": show,
            "small": small,
        }
    }


@register.simple_tag(takes_context=True)
def map_to_context(context: template.RequestContext, key: str):
    """
    Tries to get value from current context, both with key as-is and with
    dashes switched to underscores.
    """
    if key in context:
        return context[key]
    if "-" in key:
        return context.get(key.replace("-", "_"), "")
    return ""


@register.simple_tag
def static_full_uri(value: str) -> str:
    return urljoin(settings.ROOT_URL, static(value))


### FILTERS ###############################

@register.filter
def naturaltime_short(value):
    return NaturalTimeShortFormatter.string_for(value)


@register.filter(name="timedelta")
def timedelta_filter(value: Any) -> str:
    if not isinstance(value, timezone.timedelta) or not value:
        return "-"
    return timedelta_formatter(value)


@register.filter
def timedelta_rounded(value: Any) -> str:
    if not isinstance(value, timezone.timedelta):
        return "-"
    return timedelta_formatter(value, rounded=True)


@register.filter
def timedelta_rounded_short(value: Any) -> str:
    if not isinstance(value, timezone.timedelta):
        return "-"
    return timedelta_formatter(value, rounded=True, short_format=True)


@register.filter
def in_language(value: str, language_code: str) -> str:
    with override(language_code):
        return str(value)


@register.filter
def multiply(value, arg):
    try:
        return str(float(value) * float(arg))
    except Exception:
        return "-"


@register.filter
def divide_by(value, arg):
    try:
        return value / arg
    except Exception:
        return "-"


@register.filter
def subtract(value, arg):
    try:
        return value - arg
    except Exception:
        return "-"


@register.filter
def startswith(value: str, arg: str) -> bool:
    try:
        return value.startswith(arg)
    except Exception:
        return False


@register.filter
@stringfilter
def render(value: str) -> str:
    try:
        return template.Template(value).render(template.Context())
    except Exception:
        return value


@register.filter
def add_str(value, arg) -> str:
    return str(value) + str(arg)


@register.filter
def emphasize(text: str, words: Union[str, List[str]]):
    """
    Make all instances of `words` in `text` <strong>bold</strong>.
    Case insensitive.

    Details on regex: First a negative lookbehind assertion to make sure the
    current position is not preceded by a word character (i.e. we're at the
    beginning of a word). Then a match for any of our search words, OR:ed
    together. Lastly, a negative lookahead assertion to make sure we're at the
    end of a word. End result is that all case insensitive whole word matches
    of `words` in `text` will be made bold.
    """
    if isinstance(words, str):
        words = [words]
    words = [w.lower() for w in words]
    pattern = "|".join(words)
    return mark_safe(
        re.sub(rf"(?<!\w=)({pattern})(?!\w)", r"<strong>\1</strong>", text, flags=re.IGNORECASE)
    )
