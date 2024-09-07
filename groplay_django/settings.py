from dataclasses import MISSING, InitVar, dataclass, field, fields
from typing import Any, Literal

from django.conf import settings
from django.utils.functional import empty


class MissingSettingsError(Exception):
    keys: list[str]

    def __init__(self, members: str | list[str] | list["MissingSettingsError"], *args):
        print(args)
        super().__init__(*args)
        keys = []
        if not isinstance(members, list):
            members = [members]
        for member in members:
            if isinstance(member, MissingSettingsError):
                keys.extend(member.keys)
            else:
                keys.append(member)
        self.keys = keys

    def __str__(self):
        return ", ".join(self.keys)


@dataclass
class SettingsBase:
    user_settings: InitVar[Any]

    def __post_init__(self, user_settings: Any):
        errors = []

        for own_field in fields(self):
            if isinstance(user_settings, dict):
                user_setting = user_settings.get(own_field.name, empty)
            elif user_settings is not None:
                user_setting = user_settings
            else:
                user_setting = empty

            if isinstance(own_field.type, type) and issubclass(own_field.type, SettingsBase):
                try:
                    setattr(self, own_field.name, own_field.type(user_settings=user_setting))
                except MissingSettingsError as e:
                    errors.append(MissingSettingsError([f"{own_field.name}.{key}" for key in e.keys]))
            elif user_setting is not empty:
                setattr(self, own_field.name, user_setting)
            else:
                if own_field.default is MISSING and own_field.default_factory is MISSING:
                    errors.append(MissingSettingsError(own_field.name))
        if errors:
            raise MissingSettingsError(errors)


@dataclass
class RunServerSettings(SettingsBase):
    DEFAULT_ADDR: str = field(init=False, default="127.0.0.1")
    DEFAULT_PORT: str = field(init=False, default="8000")
    SERVER: Literal["django", "daphne"] = field(init=False, default="django")


@dataclass
class Settings(SettingsBase):
    RUNSERVER: RunServerSettings = field(init=False)


gd_settings = Settings(getattr(settings, "GROPLAY_DJANGO", None))
