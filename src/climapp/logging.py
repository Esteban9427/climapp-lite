"""Logging estructurado en JSON con structlog (CLAUDE.md, regla 4)."""

import structlog


def configure_logging() -> None:
    """Configura structlog para emitir un evento JSON por línea en stdout.

    Cada evento lleva `event`, `level`, `timestamp` (ISO 8601, UTC) y los campos dados.
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(default=str),  # fechas y rutas como texto
        ],
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Devuelve un logger con el nombre del módulo enlazado como `module`.

    Args:
        name: nombre lógico del emisor, normalmente `__name__`.

    Returns:
        Logger de structlog listo para `log.info("evento", campo=valor)`.
    """
    # Perezoso: los loggers de módulo se crean al importar, antes de `configure_logging`
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(module=name)
    return logger
