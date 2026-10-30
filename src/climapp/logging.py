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
            structlog.processors.JSONRenderer(),
        ],
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Devuelve un logger con el nombre del módulo enlazado como `logger`.

    Args:
        name: nombre lógico del emisor, normalmente `__name__`.

    Returns:
        Logger de structlog listo para `log.info("evento", campo=valor)`.
    """
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger().bind(logger=name)
    return logger
