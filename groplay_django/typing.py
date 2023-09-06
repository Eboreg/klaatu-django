from typing import Dict, Sequence, Tuple, Type, TypeVar

from django.forms import Form

AdminFieldsType = Sequence[str | Sequence[str]]

AdminFieldsetsType = Sequence[Tuple[str | None, Dict[str, str | AdminFieldsType]]]

_Form = TypeVar("_Form", bound=Form)

FormType = Type[_Form]
