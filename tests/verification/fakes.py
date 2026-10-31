"""Dobles de prueba del cliente Muse: nunca llaman a la red."""

from collections.abc import Iterator, Sequence
from typing import Any

from openai.types.chat import ChatCompletion

from climapp.verification.muse import Message, MuseReply, MuseTask


def completion(
    content: str | None = "{}",
    finish_reason: str = "stop",
    *,
    tool_calls: Sequence[str] = (),
    tokens: tuple[int, int] = (100, 200),
) -> ChatCompletion:
    """Respuesta del SDK `openai` armada a mano."""
    calls = [
        {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": "{}"}}
        for i, n in enumerate(tool_calls)
    ]
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return ChatCompletion.model_validate(
        {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "muse-fake",
            "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
            "usage": {
                "prompt_tokens": tokens[0],
                "completion_tokens": tokens[1],
                "total_tokens": sum(tokens),
            },
        }
    )


class FakeCompletions:
    """Imita `client.chat.completions`: guarda los argumentos y devuelve lo programado."""

    def __init__(self, *replies: ChatCompletion) -> None:
        self.calls: list[dict[str, Any]] = []
        self._replies: Iterator[ChatCompletion] = iter(replies)

    def create(self, **kwargs: Any) -> ChatCompletion:
        self.calls.append(kwargs)
        return next(self._replies)


def reply(content: str | None, finish_reason: str = "stop", **kw: Any) -> MuseReply:
    """`MuseReply` directo, para los tests de la compuerta."""
    base: dict[str, Any] = {
        "content": content,
        "finish_reason": finish_reason,
        "tool_calls": (),
        "tokens_in": 100,
        "tokens_out": 200,
        "latency_ms": 5,
        "fallback": False,
    }
    return MuseReply(**(base | kw))


class ScriptedMuse:
    """Cliente Muse que responde por tarea con una cola de respuestas programadas."""

    def __init__(self, script: dict[MuseTask, list[MuseReply]]) -> None:
        self.script = {task: list(replies) for task, replies in script.items()}
        self.requests: list[tuple[MuseTask, list[Message]]] = []

    def complete(self, task: MuseTask, messages: Sequence[Message]) -> MuseReply:
        self.requests.append((task, list(messages)))
        return self.script[task].pop(0)
