from typing import Dict, Sequence, Tuple, Type, TypeVar

from django.forms import Form

AdminFieldsType = Sequence[str | Sequence[str]]

AdminFieldsetsType = Sequence[Tuple[str | None, Dict[str, str | AdminFieldsType]]]

Form_co = TypeVar("Form_co", bound=Form)

FormType = Type[Form_co]
