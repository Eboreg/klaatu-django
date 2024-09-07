from django import forms
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorDict
from django.utils.translation import gettext as _


class CustomEmailField(forms.EmailField):
    def run_validators(self, value):
        """
        Had to override this whole thing just to be able to insert `value`
        into the error message. :-/
        """
        if value in self.empty_values:
            return
        errors = []
        for v in self.validators:
            try:
                v(value)
            except ValidationError as e:
                if hasattr(e, 'code'):
                    if e.code == "invalid":
                        e.message = _("'%(email)s' is not a valid email address.") % {"email": value}
                    elif e.code in self.error_messages:
                        e.message = self.error_messages[e.code]
                errors.extend(e.error_list)
        if errors:
            raise ValidationError(errors)


class ErrorDictFormSet(forms.BaseFormSet):
    """
    Adds utility method get_error_dict(), which converts self.errors (normally
    a list) to an ErrorDict, where the keys are (hopefully) the same as the
    "name" attributes of the form elements in the rendered formset.
    """
    def get_error_dict(self) -> ErrorDict:
        error_dict = ErrorDict()
        if self.non_form_errors():
            error_dict.update({"__all__": self.non_form_errors()})
        for idx, form_errors in enumerate(self.errors):
            assert isinstance(form_errors, ErrorDict)
            error_dict.update({
                "%s-%s" % (self.add_prefix(idx), k): v
                for k, v in form_errors.items()
            })
        return error_dict


class ErrorDictModelFormSet(ErrorDictFormSet, forms.BaseModelFormSet):
    ...
