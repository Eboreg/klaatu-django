from typing import Optional, Sequence, Type, TypeVar, Union

from django.forms import Form

AdminFieldsType = Sequence[Union[str, Sequence[str]]]

AdminFieldsetsType = Sequence[tuple[Optional[str], dict[str, Union[str, AdminFieldsType]]]]

Form_co = TypeVar("Form_co", bound=Form)

FormType = Type[Form_co]
