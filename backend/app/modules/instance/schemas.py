"""Граница контракта модуля instance."""

from pydantic import BaseModel

from app.core.enums import RegistrationMode


class InstanceInfo(BaseModel):
    """То, что видно и анониму: название и можно ли зарегистрироваться самому."""

    instance_name: str
    registration_mode: RegistrationMode
