from django import forms


class CustomCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """
    Renders a multiple checkbox select using Bootstrap's custom control layout:
    https://getbootstrap.com/docs/4.6/components/forms/#checkboxes-and-radios-1

    `field_wrapper_class` is for a <div> wrapping the entire widget.
    `option_wrapper_class` is for <div>'s wrapping each individual checkbox.

    Responsive layout example:

    CustomCheckboxSelectMultiple(
        field_wrapper_class="row",
        option_wrapper_class="col-12 col-lg-6"
    )
    """
    template_name = "klaatu/widgets/custom_checkbox_select.html"
    field_wrapper_class = ""
    option_wrapper_class = ""

    def __init__(self, attrs=None, choices=(), field_wrapper_class="", option_wrapper_class=""):
        super().__init__(attrs, choices)
        self.field_wrapper_class = field_wrapper_class
        self.option_wrapper_class = option_wrapper_class

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if "class" in option["attrs"]:
            option["attrs"]["class"] += " form-check-input"
        else:
            option["attrs"]["class"] = "form-check-input"
        return option

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"].update(
            field_wrapper_class=self.field_wrapper_class,
            option_wrapper_class=self.option_wrapper_class,
        )
        return context
