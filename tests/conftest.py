"""Fixtures compartidos: entorno aislado de las variables reales del operador."""

from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"


def env_example_items() -> dict[str, str]:
    """Devuelve las claves y valores de `.env.example`, sin comentarios."""
    items: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            items[key.strip()] = value.strip()
    return items


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Quita del entorno las claves de configuración para que no contaminen los tests."""
    for key in env_example_items():
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    """Archivo `.env` completo, copiado de `.env.example` con `DATA_DIR` apuntando a tmp."""
    items = env_example_items() | {"DATA_DIR": str(tmp_path / "data")}
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in items.items()), encoding="utf-8")
    return path


def rewrite_env(path: Path, **changes: str | None) -> Path:
    """Reescribe `path` cambiando claves (`None` borra la clave)."""
    items = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())
    for key, value in changes.items():
        if value is None:
            items.pop(key, None)
        else:
            items[key] = value
    path.write_text("\n".join(f"{k}={v}" for k, v in items.items()), encoding="utf-8")
    return path
