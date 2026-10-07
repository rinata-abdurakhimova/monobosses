"""FastAPI application (contract v1). R2-01: mock handlers only, no real analysis."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from vic.api import cases, evidence, health, reports, runs
from vic.config import get_settings
from vic.errors import register_error_handlers

API_VERSION = "0.1.0"


def build_openapi(app: FastAPI) -> dict:
    """OpenAPI schema where 422 uses the shared error envelope instead of FastAPI's default."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes,
                         description="Contract v1. R2-01: mock handlers only.")
    components = schema.get("components", {}).get("schemas", {})
    envelope_ref = {"$ref": "#/components/schemas/ErrorEnvelope"}
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            responses = operation.get("responses", {})
            if "422" in responses:
                responses["422"] = {"description": "Validation error",
                                    "content": {"application/json": {"schema": envelope_ref}}}
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    app = FastAPI(title="Virtual Investment Committee API", version=API_VERSION)
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-VIC-Mock"])
    register_error_handlers(app)
    for module in (health, cases, runs, reports, evidence):
        app.include_router(module.router)
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()