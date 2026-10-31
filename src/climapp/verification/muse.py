"""Cliente de Muse Spark (Meta Model API, compatible con el SDK `openai`) y fallback grabado.

ADR-002 §1, §2 y §5: `base_url`, clave, modelo y esfuerzo por tarea salen de `Settings`;
`max_tokens` es siempre `MUSE_MAX_TOKENS` (≥ 2000, porque el razonamiento consume la
salida). Con `DEMO_FALLBACK=1` se usan respuestas grabadas que pasan por la misma
compuerta y se marcan `fallback=true`.
"""

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast

import openai
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, ConfigDict, Field

from climapp.config import Effort, Settings
from climapp.logging import get_logger

log = get_logger(__name__)
Message = Mapping[str, str]
HASH_HEX_CHARS = 16  # 64 bits de SHA-256: basta para distinguir unas pocas grabaciones


class MuseTask(StrEnum):
    """Tareas de Muse Spark, cada una con su esfuerzo de razonamiento (ADR-002 §2)."""

    STRUCTURE = "estructurar"
    EXPLAIN = "explicar"
    JUDGE = "juez"


class MuseError(Exception):
    """Falla al obtener una respuesta de Muse (red, API o grabación inexistente)."""


@dataclass(frozen=True, slots=True)
class MuseReply:
    """Respuesta de Muse reducida a lo que usa la compuerta.

    Attributes:
        content: texto de la respuesta; `None` si vino vacía.
        finish_reason: motivo de fin (`stop`, `length`, `tool_calls`…).
        tool_calls: nombres de las herramientas que pidió el modelo.
        tokens_in: tokens de entrada.
        tokens_out: tokens de salida (incluye el razonamiento).
        latency_ms: latencia de la llamada.
        fallback: `True` si es una respuesta grabada (`DEMO_FALLBACK=1`).
    """

    content: str | None
    finish_reason: str
    tool_calls: tuple[str, ...]
    tokens_in: int
    tokens_out: int
    latency_ms: int
    fallback: bool


class MuseClient(Protocol):
    """Lo que la compuerta necesita de un cliente Muse."""

    def complete(self, task: MuseTask, messages: Sequence[Message]) -> MuseReply:
        """Pide una respuesta para `messages` con los parámetros de `task`."""
        ...


class Completions(Protocol):
    """Subconjunto de `openai.OpenAI().chat.completions` que se usa."""

    def create(self, **kwargs: Any) -> ChatCompletion:
        """Crea una respuesta de chat."""
        ...


@dataclass(frozen=True, slots=True)
class MuseParams:
    """Modelo, `max_tokens` y esfuerzo por tarea (desde `Settings`)."""

    model: str
    max_tokens: int
    efforts: Mapping[MuseTask, Effort]

    @classmethod
    def from_settings(cls, settings: Settings) -> "MuseParams":
        """Toma `MUSE_MODEL`, `MUSE_MAX_TOKENS` y `MUSE_EFFORT_*`."""
        efforts: dict[MuseTask, Effort] = {
            MuseTask.STRUCTURE: settings.muse_effort_structure,
            MuseTask.EXPLAIN: settings.muse_effort_explain,
            MuseTask.JUDGE: settings.muse_effort_judge,
        }
        return cls(settings.muse_model, settings.muse_max_tokens, efforts)


def _reply(response: ChatCompletion, latency_ms: int) -> MuseReply:
    """Reduce la respuesta del SDK a `MuseReply`."""
    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    calls = (message.tool_calls or []) if message else []
    usage = response.usage
    return MuseReply(
        content=message.content if message else None,
        finish_reason=(choice.finish_reason or "") if choice else "",
        tool_calls=tuple(getattr(c, "function", c).name for c in calls),  # type: ignore[union-attr]
        tokens_in=usage.prompt_tokens if usage else 0,
        tokens_out=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
        fallback=False,
    )


class LiveMuseClient:
    """Cliente real: una llamada a `chat.completions.create` por pedido."""

    def __init__(
        self,
        completions: Completions,
        params: MuseParams,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Guarda el endpoint de completions, los parámetros y el reloj de latencia."""
        self._completions, self._params, self._clock = completions, params, clock

    def complete(self, task: MuseTask, messages: Sequence[Message]) -> MuseReply:
        """Llama a Muse con el esfuerzo de `task` y `max_tokens = MUSE_MAX_TOKENS`.

        Raises:
            MuseError: si la API falla (red, tiempo agotado o estado HTTP de error).
        """
        start = self._clock()
        try:
            response = self._completions.create(
                model=self._params.model,
                messages=list(messages),
                reasoning_effort=self._params.efforts[task],
                max_tokens=self._params.max_tokens,
            )
        except openai.APIError as err:
            msg = f"Muse falló en la tarea {task.value}: {type(err).__name__}"
            raise MuseError(msg) from err
        reply = _reply(response, round((self._clock() - start) * 1000))
        log.info(
            "muse.reply",
            task=task.value,
            finish=reply.finish_reason,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            latency_ms=reply.latency_ms,
        )
        return reply


class Recording(BaseModel):
    """Respuesta real grabada para el fallback (`MUSE_FALLBACK_FILE`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: MuseTask
    request_hash: str | None
    model: str
    recorded_at: datetime
    content: str | None
    finish_reason: str
    tool_calls: list[str]
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class _RecordingFile(BaseModel):
    """Archivo de grabaciones."""

    model_config = ConfigDict(extra="forbid")

    recordings: list[Recording]


def request_hash(task: MuseTask, messages: Sequence[Message]) -> str:
    """Clave estable de un pedido: SHA-256 de la tarea y los mensajes, abreviado."""
    payload = json.dumps([task.value, [dict(m) for m in messages]], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:HASH_HEX_CHARS]


def load_recordings(path: Path) -> list[Recording]:
    """Lee las grabaciones del fallback.

    Raises:
        OSError: si el archivo no se puede leer.
        pydantic.ValidationError: si el archivo no tiene el formato esperado.
    """
    return _RecordingFile.model_validate_json(path.read_bytes()).recordings


class RecordedMuseClient:
    """Cliente de demo: devuelve respuestas grabadas, siempre con `fallback=True`."""

    def __init__(self, recordings: Sequence[Recording]) -> None:
        """Guarda las grabaciones en el orden del archivo."""
        self._recordings = list(recordings)

    def complete(self, task: MuseTask, messages: Sequence[Message]) -> MuseReply:
        """La grabación del mismo pedido o, si no hay, la primera de la tarea.

        Raises:
            MuseError: si no hay ninguna grabación para la tarea.
        """
        digest = request_hash(task, messages)
        same_task = [r for r in self._recordings if r.task is task]
        exact = [r for r in same_task if r.request_hash == digest]
        if not same_task:
            msg = f"no hay respuestas grabadas para la tarea {task.value}"
            raise MuseError(msg)
        rec = (exact or same_task)[0]
        log.info("muse.fallback", task=task.value, exact=bool(exact))
        return MuseReply(
            rec.content,
            rec.finish_reason,
            tuple(rec.tool_calls),
            rec.tokens_in,
            rec.tokens_out,
            rec.latency_ms,
            fallback=True,
        )


def build_client(settings: Settings) -> MuseClient:
    """Cliente según `DEMO_FALLBACK`: grabado (1) o real contra `META_API_BASE_URL` (0).

    Raises:
        OSError, pydantic.ValidationError: si el archivo de grabaciones no es válido.
    """
    if settings.demo_fallback:
        return RecordedMuseClient(load_recordings(settings.muse_fallback_file))
    client = openai.OpenAI(
        base_url=settings.meta_api_base_url,
        api_key=settings.meta_api_key.get_secret_value(),
        timeout=settings.muse_timeout_s,
        max_retries=0,  # los reintentos los decide la compuerta (ADR-002 §3)
    )
    completions = cast(Completions, client.chat.completions)  # frontera con el SDK
    return LiveMuseClient(completions, MuseParams.from_settings(settings))
