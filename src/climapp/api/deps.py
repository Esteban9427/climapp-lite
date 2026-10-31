"""Dependencias compartidas de la API: configuración, reloj y error de negocio."""

from datetime import UTC, datetime
from functools import cache
from typing import Annotated

from fastapi import Depends

from climapp.config import Settings


class ApiError(Exception):
    """Error de negocio que se responde como `{code, message}`."""

    def __init__(self, status: int, code: str, message: str) -> None:
        """Guarda el código HTTP y el error del contrato."""
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@cache
def get_settings() -> Settings:
    """Configuración leída una vez de `.env` (se reemplaza en los tests)."""
    return Settings()


def get_now() -> datetime:
    """Instante actual con zona (se reemplaza en los tests)."""
    return datetime.now(UTC)


SettingsDep = Annotated[Settings, Depends(get_settings)]
NowDep = Annotated[datetime, Depends(get_now)]
