from typing import Dict, Optional, Sequence, Tuple, Type, TypeVar, Union

from django.forms import Form

AdminFieldsType = Sequence[Union[str, Sequence[str]]]

AdminFieldsetsType = Sequence[Tuple[Optional[str], Dict[str, Union[str, AdminFieldsType]]]]

Form_co = TypeVar("Form_co", bound=Form)

FormType = Type[Form_co]
