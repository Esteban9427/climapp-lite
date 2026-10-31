"""Tests del cliente Muse y del fallback grabado (TASK-011, ADR-002 §1, §2 y §5)."""

import json
from pathlib import Path

import openai
import pytest
from pydantic import ValidationError

from climapp.config import Settings
from climapp.verification.muse import (
    LiveMuseClient,
    MuseError,
    MuseParams,
    MuseTask,
    RecordedMuseClient,
    build_client,
    load_recordings,
    request_key,
)
from tests.conftest import rewrite_env
from tests.verification.fakes import FakeCompletions, completion

PARAMS = MuseParams(
    model="muse-test",
    max_tokens=2000,
    efforts={MuseTask.STRUCTURE: "low", MuseTask.EXPLAIN: "low", MuseTask.JUDGE: "medium"},
)
MESSAGES = [{"role": "user", "content": "llueve fuerte en la vereda"}]


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        self.t += 0.25
        return self.t


@pytest.mark.parametrize(
    ("task", "effort"),
    [(MuseTask.STRUCTURE, "low"), (MuseTask.EXPLAIN, "low"), (MuseTask.JUDGE, "medium")],
)
def test_sends_model_effort_per_task_and_max_tokens(task: MuseTask, effort: str) -> None:
    fake = FakeCompletions(completion())
    LiveMuseClient(fake, PARAMS).complete(task, MESSAGES)
    (call,) = fake.calls
    assert call["model"] == "muse-test"
    assert call["messages"] == MESSAGES
    assert call["reasoning_effort"] == effort
    assert call["max_tokens"] == 2000


def test_maps_content_finish_reason_tokens_tools_and_latency() -> None:
    fake = FakeCompletions(completion("hola", "length", tool_calls=["buscar"], tokens=(120, 340)))
    out = LiveMuseClient(fake, PARAMS, clock=_Clock()).complete(MuseTask.JUDGE, MESSAGES)
    assert (out.content, out.finish_reason, out.tool_calls) == ("hola", "length", ("buscar",))
    assert (out.tokens_in, out.tokens_out, out.latency_ms) == (120, 340, 250)
    assert out.fallback is False


def test_api_errors_are_raised_as_muse_error_with_context() -> None:
    class Failing:
        def create(self, **_: object) -> object:
            raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]

    with pytest.raises(MuseError, match="juez"):
        LiveMuseClient(Failing(), PARAMS).complete(MuseTask.JUDGE, MESSAGES)  # type: ignore[arg-type]


def test_params_come_from_settings(env_file: Path) -> None:
    rewrite_env(env_file, MUSE_MODEL="m-x", MUSE_EFFORT_EXPLAIN="medium", MUSE_MAX_TOKENS="2500")
    params = MuseParams.from_settings(Settings(_env_file=env_file))
    assert params.model == "m-x"
    assert params.max_tokens == 2500
    assert params.efforts == {
        MuseTask.STRUCTURE: "low",
        MuseTask.EXPLAIN: "medium",
        MuseTask.JUDGE: "medium",
    }


def _recordings(tmp_path: Path, *entries: dict[str, object]) -> Path:
    path = tmp_path / "rec.json"
    path.write_text(json.dumps({"recordings": list(entries)}), encoding="utf-8")
    return path


def _entry(task: str, content: str, key: str | None = None) -> dict[str, object]:
    return {
        "task": task,
        "key": key,
        "model": "muse-spark-1.3",
        "recorded_at": "2026-10-31T12:00:00-05:00",
        "content": content,
        "finish_reason": "stop",
        "tool_calls": [],
        "tokens_in": 10,
        "tokens_out": 20,
        "latency_ms": 900,
    }


def test_recorded_client_returns_the_exact_recording_marked_fallback(tmp_path: Path) -> None:
    key = request_key(MuseTask.JUDGE, MESSAGES)
    path = _recordings(tmp_path, _entry("juez", "otro"), _entry("juez", "exacta", key))
    out = RecordedMuseClient(load_recordings(path)).complete(MuseTask.JUDGE, MESSAGES)
    assert out.content == "exacta"
    assert out.fallback is True
    assert (out.tokens_in, out.tokens_out, out.latency_ms) == (10, 20, 900)


def test_recorded_client_falls_back_to_the_first_recording_of_the_task(tmp_path: Path) -> None:
    path = _recordings(tmp_path, _entry("estructurar", "e1"), _entry("juez", "j1"))
    client = RecordedMuseClient(load_recordings(path))
    assert client.complete(MuseTask.JUDGE, [{"role": "user", "content": "otro"}]).content == "j1"


def test_recorded_client_without_recording_for_the_task_fails(tmp_path: Path) -> None:
    client = RecordedMuseClient(load_recordings(_recordings(tmp_path, _entry("juez", "j"))))
    with pytest.raises(MuseError, match="explicar"):
        client.complete(MuseTask.EXPLAIN, MESSAGES)


def test_request_key_depends_on_task_and_messages() -> None:
    other = [{"role": "user", "content": "otro"}]
    assert request_key(MuseTask.JUDGE, MESSAGES) == request_key(MuseTask.JUDGE, list(MESSAGES))
    assert request_key(MuseTask.JUDGE, MESSAGES) != request_key(MuseTask.EXPLAIN, MESSAGES)
    assert request_key(MuseTask.JUDGE, MESSAGES) != request_key(MuseTask.JUDGE, other)


def test_invalid_recording_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_recordings(_recordings(tmp_path, {"task": "juez"}))


def test_build_client_uses_recordings_with_demo_fallback(env_file: Path, tmp_path: Path) -> None:
    path = _recordings(tmp_path, _entry("juez", "j"))
    rewrite_env(env_file, DEMO_FALLBACK="1", MUSE_FALLBACK_FILE=str(path))
    assert isinstance(build_client(Settings(_env_file=env_file)), RecordedMuseClient)


def test_build_client_is_live_without_demo_fallback(env_file: Path) -> None:
    rewrite_env(env_file, DEMO_FALLBACK="0", META_API_KEY="clave-falsa")
    assert isinstance(build_client(Settings(_env_file=env_file)), LiveMuseClient)
