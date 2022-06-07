import warnings
from typing import Any, List, Optional, Union

from rest_framework import serializers
from rest_framework.compat import uritemplate
from rest_framework.exceptions import APIException
from rest_framework.fields import CharField, ChoiceField, EmailField, IntegerField, empty
from rest_framework.schemas.openapi import AutoSchema, SchemaGenerator as _SchemaGenerator
from rest_framework.schemas.utils import get_pk_description, is_list_view

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields import NOT_PROVIDED
from django.utils.encoding import force_str


class ExtraResponse:
    code: str
    key: str
    description: str
    example: Any

    def __init__(self, code: Union[str, int], key: str, description: str, example: Any = None):
        self.code = str(code) if isinstance(code, int) else code
        self.key = key
        self.description = description
        self.example = example


class Extra404Response(ExtraResponse):
    def __init__(self, key='not_found', description='Object not found', example=None):
        example = example or {'error': ['Not found.']}
        super().__init__(code=404, key=key, description=description, example=example)


class BaseSchemaGenerator(_SchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.update({
            'security': self.get_security(),
            'tags': self.get_tags(),
            'servers': self.get_servers(),
        })
        if 'components' not in schema:
            schema['components'] = {}
        schema['components']['securitySchemes'] = {}
        for sec_def in schema.get('security', {}):
            for k in sec_def.keys():
                schema['components']['securitySchemes'][k] = self.get_security_scheme(k)
        return schema

    def get_servers(self):
        return [{'url': settings.ROOT_URL}]

    def get_security(self):
        """
        Returns a list of security requirement objects, as per:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.0.3.md#securityRequirementObject

        Object names should be the class names of object names returned by
        a view's get_authenticators() method.

        Each object name should correspond to a scheme returned by
        self.get_security_scheme().
        """
        return []

    def get_security_scheme(self, name):
        """
        Returns a security scheme object, as per:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.0.3.md#securitySchemeObject
        """
        return {}

    def get_tags(self):
        """
        Returns a list of tag objects, as per:
        https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.0.3.md#tagObject
        """
        return []


class BaseSchemaMixin:
    operation_description = ''
    operation_summary: Optional[str] = None
    optional_response_fields: dict
    view: Any

    def __init__(self, tags=None, operation_id_base=None, component_name=None, **kwargs):
        if 'optional_response_fields' in kwargs:
            self.optional_response_fields = kwargs.pop('optional_response_fields')
        elif not hasattr(self, 'optional_response_fields'):
            self.optional_response_fields = {}
        for key, value in kwargs.items():
            setattr(self, key, value)
        super().__init__(tags=tags, operation_id_base=operation_id_base, component_name=component_name)  # type: ignore

    def collect_extra_responses(self, path, method):
        responses = {}
        response: dict
        for extra_response in self.get_extra_responses(path, method):
            if extra_response.code not in responses:
                response = {
                    'description': extra_response.description,
                    'content': {'application/json': {'examples': {}}},
                }
                responses[extra_response.code] = response
            else:
                response = responses[extra_response.code]
                if response['description']:
                    response['description'] = 'Multiple reasons'
                else:
                    response['description'] = extra_response.description
            if extra_response.example:
                response['content']['application/json']['examples'].update({
                    extra_response.key: {
                        'description': extra_response.description,
                        'value': extra_response.example,
                    }
                })
        return responses

    def get_action(self) -> Optional[str]:
        if hasattr(self, 'view'):
            return getattr(self.view, 'action', None)
        return None

    def get_extra_responses(self, path, method) -> List[ExtraResponse]:
        responses = []

        if method in ('POST', 'PUT', 'PATCH'):
            missing_fields = {}
            non_null_fields = {}
            non_blank_fields = {}
            choice_fields = {}
            max_length_fields = {}
            min_length_fields = {}
            max_value_fields = {}
            min_value_fields = {}
            email_fields = {}
            serializer = self.view.get_serializer(path, method)
            for field_name, field in serializer.fields.items():
                if not field.read_only:
                    if field.required and method != 'PATCH':
                        missing_fields[field_name] = ['This field is required.']
                    if not field.allow_null:
                        non_null_fields[field_name] = ['This field may not be null.']
                    if isinstance(field, CharField) and not field.allow_blank:
                        non_blank_fields[field_name] = ['This field may not be blank.']
                    if isinstance(field, CharField):
                        if field.max_length is not None:
                            max_length_fields[field_name] = [
                                f'Ensure this field has no more than {field.max_length} characters.'
                            ]
                        if field.min_length is not None and field.min_length > 1:
                            min_length_fields[field_name] = [
                                f'Ensure this field has at least {field.min_length} characters.'
                            ]
                    if isinstance(field, IntegerField):
                        if field.min_value is not None:
                            min_value_fields[field_name] = [
                                f'Ensure this value is greater than or equal to {field.min_value}.'
                            ]
                        if field.max_value is not None:
                            max_value_fields[field_name] = [
                                f'Ensure this value is less than or equal to {field.max_value}.'
                            ]
                    if isinstance(field, ChoiceField):
                        choice_fields[field_name] = ['"foo" is not a valid choice.']
                    if isinstance(field, EmailField):
                        email_fields[field_name] = ['Enter a valid email address.']
            if missing_fields:
                responses.append(ExtraResponse(400, 'missing_fields', 'Missing fields', missing_fields))
            if non_null_fields:
                responses.append(ExtraResponse(400, 'non_null_fields', 'Non-nullable fields', non_null_fields))
            if non_blank_fields:
                responses.append(ExtraResponse(400, 'non_blank_fields', 'Non-blankable fields', non_blank_fields))
            if choice_fields:
                responses.append(ExtraResponse(400, 'invalid_choices', 'Invalid enum choices', choice_fields))
            if max_length_fields:
                responses.append(ExtraResponse(
                    400,
                    'max_length_exceeded',
                    'Maximum string length exceeded',
                    max_length_fields
                ))
            if min_length_fields:
                responses.append(ExtraResponse(
                    400,
                    'min_length_subceeded',
                    'Minimum string length subceeded',
                    min_length_fields
                ))
            if email_fields:
                responses.append(ExtraResponse(400, 'invalid_email', 'Invalid email address', email_fields))
            if min_value_fields:
                responses.append(ExtraResponse(
                    400,
                    'min_value_subceeded',
                    'Minimum integer value subceeded',
                    min_value_fields
                ))
            if max_value_fields:
                responses.append(ExtraResponse(
                    400,
                    'max_value_exceeded',
                    'Maximum integer value exceeded',
                    max_value_fields
                ))
        return responses

    def get_operation_summary(self, path, method):
        return self.operation_summary

    def get_optional_response_fields(self, path, method):
        fields = set()
        if method in self.optional_response_fields:
            fields.update(self.optional_response_fields[method])
        if 'default' in self.optional_response_fields:
            fields.update(self.optional_response_fields['default'])
        return list(fields)

    def get_path_parameter_description(self, path, method, variable):
        return None

    def get_path_parameter_type(self, path, method, variable):
        return 'string'

    def collect_extra_response_field_attributes(self, path, method, schema, field_name):
        schema.update(self.get_extra_response_field_attributes(path, method, field_name))
        properties = None
        if schema.get('type', '') == 'array' and 'items' in schema:
            if schema['items'].get('type', '') == 'object' and 'properties' in schema['items']:
                properties = schema['items']['properties']
        elif schema.get('type', '') == 'object' and 'properties' in schema:
            properties = schema['properties']
        if properties:
            for subname, subschema in properties.items():
                self.collect_extra_response_field_attributes(path, method, subschema, f'{field_name}.{subname}')

    def get_extra_response_field_attributes(self, path, method, field_name):
        """
        For use when we want to put some arbitrary attributes on a response
        field, like "deprecated".

        :param field_name: A "composite" fieldname, consisting of period
        separated fieldnames, e.g. `sections.file.url`.
        """
        return {}

    def get_security(self, path, method):
        return [{auth.__class__.__name__: []} for auth in self.view.get_authenticators()]

    def is_list_view(self, path, method):
        return is_list_view(path, method, self.view)

    def map_model_field(self, field):
        # Used to describe path parameters
        if isinstance(field, (models.AutoField, models.IntegerField)):
            schema = {'type': 'integer'}
        elif isinstance(field, models.BinaryField):
            schema = {'type': 'string', 'format': 'binary'}
        elif isinstance(field, models.BooleanField):
            schema = {'type': 'boolean'}
        elif isinstance(field, models.DateTimeField):
            schema = {'type': 'string', 'format': 'date-time'}
        elif isinstance(field, models.DateField):
            schema = {'type': 'string', 'format': 'date'}
        elif isinstance(field, models.TimeField):
            schema = {'type': 'string', 'format': 'time'}
        elif isinstance(field, (models.DecimalField, models.FloatField)):
            schema = {'type': 'number', 'format': 'float'}
        elif isinstance(field, models.URLField):
            schema = {'type': 'string', 'format': 'uri'}
        elif isinstance(field, models.EmailField):
            schema = {'type': 'string', 'format': 'email'}
        elif isinstance(field, models.UUIDField):
            schema = {'type': 'string', 'format': 'uuid'}
        else:
            schema = {'type': 'string'}
        if field.null:
            schema['nullable'] = True  # type: ignore
        return schema


class BaseSchema(BaseSchemaMixin, AutoSchema):
    operation_tags: list = []
    # Field schemas must contain "type" key. Key "format" is also common,
    # and we may want a "description".
    # https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.3.md#schema-object
    serializer_field_schemas: dict = {}

    def __init__(self, tags=None, operation_id_base=None, component_name=None, **kwargs):
        operation_id_base = operation_id_base or getattr(self, 'operation_id_base', None)
        super().__init__(tags=tags, operation_id_base=operation_id_base, component_name=component_name, **kwargs)

    def get_description(self, path, method):
        return self.operation_description or super().get_description(path, method)

    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        operation['summary'] = self.get_operation_summary(path, method) or operation['operationId']
        operation['security'] = self.get_security(path, method)
        return operation

    def get_operation_id(self, path, method):
        # It's ugly when not all ID's get uppercase first letter
        id_: str = super().get_operation_id(path, method)
        return id_[0].upper() + id_[1:]

    def get_path_parameters(self, path, method):
        # Had to override the whole thing to fix the check for model, get
        # custom descriptions & type, and check for model field type
        assert uritemplate, '`uritemplate` must be installed for OpenAPI schema support.'
        # My fix #1 (OK, somewhat messy):
        try:
            model = self.view.serializer_class.Meta.model
        except AttributeError:
            try:
                model = self.view.queryset.model
            except AttributeError:
                model = None

        parameters = []
        for variable in uritemplate.variables(path):
            # My fix #2:
            description = self.get_path_parameter_description(path, method, variable)
            schema = {'type': self.get_path_parameter_type(path, method, variable)}
            if model is not None:
                try:
                    model_field = model._meta.get_field(variable)
                except (FieldDoesNotExist, KeyError):
                    model_field = None
                if model_field is not None:
                    # Custom descriptions take precedence
                    if description is None and model_field.help_text:
                        description = force_str(model_field.help_text)
                    elif description is None and model_field.primary_key:
                        description = get_pk_description(model, model_field)
                    schema = self.map_model_field(model_field)
                    # Really makes no sense to mark path parameters as nullable
                    schema.pop('nullable', None)
            parameter = {
                'name': variable,
                'in': 'path',
                'required': True,
                'description': description or '',
                'schema': schema,
            }
            parameters.append(parameter)
        return parameters

    def get_request_body(self, path, method):
        # Default implementation just gets a reference and returns
        # {"schema": {"$ref": "#/components/schemas/..."}} for each content
        # type. However, this makes the request body identical for POST, PUT,
        # and PATCH, and we don't want that; for PATCH, _no_ parameters should
        # be marked as "required".
        if method not in ('PUT', 'PATCH', 'POST'):
            return {}
        self.request_media_types = self.map_parsers(path, method)
        serializer = self.get_serializer(path, method)
        if isinstance(serializer, serializers.ListSerializer):
            serializer = serializer.child
            is_list = True
        else:
            is_list = False
        if not isinstance(serializer, serializers.Serializer):
            item_schema = {}
        else:
            item_schema = self.map_serializer(serializer)
            if method == 'PATCH':
                item_schema['required'] = []
                for key, prop in item_schema.get('properties', {}).items():
                    if isinstance(prop, dict) and 'type' in prop:
                        if prop['type'] == 'object':
                            item_schema['properties'][key]['required'] = []
                        if prop['type'] == 'array' and 'items' in prop:
                            item_schema['properties'][key]['items']['required'] = []
        if is_list:
            request_schema = {
                'type': 'array',
                'items': item_schema,
            }
        else:
            request_schema = item_schema
        return {
            'content': {
                ct: {'schema': request_schema} for ct in self.request_media_types
            }
        }

    def get_responses(self, path, method):
        # Had to override the whole shit to inject specific response
        # descriptions
        is_list = False
        if method == 'DELETE':
            return {
                '204': {'description': 'Object successfully deleted'},
                **self.collect_extra_responses(path, method),
            }
        self.response_media_types = self.map_renderers(path, method)
        if self.is_list_view(path, method):
            serializer = self.get_serializer(path, method, many=True)
            is_list = True
        else:
            serializer = self.get_serializer(path, method)
        if isinstance(serializer, serializers.Serializer):
            item_schema = self.map_serializer(serializer)
        elif isinstance(serializer, serializers.ListSerializer) and \
                isinstance(serializer.child, serializers.BaseSerializer):
            item_schema = self.map_serializer(serializer.child)
            is_list = True
        else:
            item_schema = {}
        # Injected thing; all response fields are considered "required"
        # per default, put exceptions in self.optional_response_fields
        if 'properties' in item_schema:
            item_schema['required'] = [
                f for f in item_schema['properties'] if f not in self.get_optional_response_fields(path, method)]
            for name, schema in item_schema['properties'].copy().items():
                if 'writeOnly' in schema:
                    del item_schema['properties'][name]
                    continue
                if 'default' not in schema:
                    try:
                        if isinstance(serializer, serializers.ListSerializer):
                            model_field = serializer.child.Meta.model._meta.get_field(name)  # type: ignore
                        else:
                            model_field = serializer.Meta.model._meta.get_field(name)
                        if model_field.default != NOT_PROVIDED and not callable(model_field.default):
                            item_schema['properties'][name]['default'] = model_field.default
                    except (FieldDoesNotExist, AttributeError):
                        pass
                # Injected thing:
                self.collect_extra_response_field_attributes(path, method, schema, name)
        if is_list:
            response_schema = {
                'type': 'array',
                'items': item_schema,
            }
            paginator = self.get_paginator()
            if paginator:
                response_schema = paginator.get_paginated_response_schema(response_schema)  # type: ignore
        else:
            response_schema = item_schema
        if method == 'POST':
            code = '201'
        else:
            code = '200'
        return {
            code: {
                'content': {
                    ct: {'schema': response_schema}
                    for ct in self.response_media_types
                },
                'description': ''
            },
            **self.collect_extra_responses(path, method),
        }

    def get_serializer(self, path, method, many=False):
        # Mock Request object because some serializers depend on method
        class MockRequest:
            method: str
            user: AnonymousUser

        self.view.request = MockRequest()
        self.view.request.method = method
        self.view.request.user = AnonymousUser()

        if many:
            try:
                return self.view.get_serializer(many=many)
            except (APIException, AttributeError):
                warnings.warn(
                    f'{self.view.__class__.__name__}.get_serializer() raised an exception during schema generation. '
                    f'Serializer fields will not be generated for {method} {path}.'
                )
                return None
        return super().get_serializer(path, method)

    def get_tags(self, path, method):
        return [t.name for t in self.operation_tags]

    def map_choicefield(self, field):
        # Patch to handle TextChoices and IntegerChoices objects
        mapping = super().map_choicefield(field)
        if 'type' in mapping:
            if mapping['type'] == 'string':
                mapping['enum'] = [str(v) for v in mapping['enum']]
            elif mapping['type'] == 'integer':
                mapping['enum'] = [int(v) for v in mapping['enum']]
        return mapping

    def map_field(self, field):
        field_schema: dict = {}

        # Overriding to check for pk_field and PK model field types
        if isinstance(field, serializers.PrimaryKeyRelatedField):
            model = getattr(field.queryset, 'model', None)
            if model is not None:
                field_schema = self.map_model_field(model._meta.pk)
            elif field.pk_field is not None:
                field_schema = self.map_field(field.pk_field)

        if not field_schema:
            field_schema = super().map_field(field)
        if field.field_name in self.serializer_field_schemas:
            field_schema.update(self.serializer_field_schemas[field.field_name])
        if field.default and field.default != empty and not callable(field.default):
            # This is also done in map_serializer(), but I have to do it here
            # so I can also do the check for model field default below
            field_schema['default'] = field.default
        else:
            try:
                model_field = field.parent.Meta.model._meta.get_field(field.field_name)
                if model_field.default != NOT_PROVIDED and not callable(model_field.default):
                    field_schema['default'] = model_field.default
            except (FieldDoesNotExist, AttributeError):
                pass
        return field_schema


### MIXINS #####################################

class ModelViewMixin(BaseSchemaMixin):
    object_name: str
    object_name_plural: str
    view: Any

    def get_operation_summary(self, path, method):
        if self.operation_summary is not None:
            return self.operation_summary
        object_name = getattr(self, 'object_name', None)
        object_name_plural = getattr(self, 'object_name_plural', None)
        if not object_name_plural:
            object_name_plural = object_name
        if not object_name:
            serializer = self.get_serializer(path, method)  # type: ignore
            if hasattr(serializer, 'Meta'):
                if not object_name:
                    object_name = serializer.Meta.model._meta.verbose_name
                if not object_name_plural:
                    object_name_plural = serializer.Meta.model._meta.verbose_name_plural
            else:
                return None
        if method == 'GET':
            if self.is_list_view(path, method):
                return f'List {object_name_plural}'
            else:
                return f'Get {object_name}'
        if method == 'POST':
            return f'Create {object_name}'
        if method == 'PUT':
            return f'Update {object_name}'
        if method == 'PATCH':
            return f'Patch {object_name}'
        if method == 'DELETE':
            return f'Delete {object_name}'

    def get_404_response(self, path, method):
        """Refers to the object fetched by view.get_object()"""
        serializer = self.get_serializer(path, method)  # type: ignore
        example = None
        object_name = self.view.get_queryset().model._meta.object_name
        if not object_name and hasattr(serializer, 'Meta') and serializer.Meta.model:
            object_name = serializer.Meta.model._meta.object_name
        if object_name:
            example = {'error': [f'No {object_name} matches the given query.']}
        return Extra404Response(example=example)

    def get_extra_responses(self, path, method):
        responses = super().get_extra_responses(path, method)
        if method == 'POST' or (method == 'GET' and self.is_list_view(path, method)):
            return responses
        _404_response = self.get_404_response(path, method)
        if _404_response:
            responses.append(_404_response)
        return responses
