"""Validación de respuestas contra `docs/openapi.yaml` (fuente de verdad del contrato)."""

from functools import cache
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from tests.conftest import ROOT

SPEC_URI = "urn:climapp:openapi"


@cache
def spec() -> dict[str, Any]:
    """Documento OpenAPI cargado una vez."""
    loaded: dict[str, Any] = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text("utf-8"))
    return loaded


def assert_matches(body: object, schema_name: str) -> None:
    """Falla si `body` no cumple `components.schemas.<schema_name>`."""
    resource = Resource.from_contents(spec(), default_specification=DRAFT202012)
    registry: Registry[Any] = Registry().with_resource(SPEC_URI, resource)
    schema = {"$ref": f"{SPEC_URI}#/components/schemas/{schema_name}"}
    Draft202012Validator(schema, registry=registry).validate(body)


def documented_statuses(path: str, method: str = "get") -> set[int]:
    """Códigos de respuesta documentados para una ruta."""
    return {int(code) for code in spec()["paths"][path][method]["responses"]}
