from typing import Sequence, TypeVar

from django.forms import Form

AdminFieldsType = Sequence[str | Sequence[str]]

AdminFieldsetsType = Sequence[tuple[str | None, dict[str, str | AdminFieldsType]]]

_Form = TypeVar("_Form", bound=Form)

FormType = type[_Form]
