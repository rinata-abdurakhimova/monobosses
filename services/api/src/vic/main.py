"""FastAPI application (contract v1)."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from vic.api import cases, evidence, health, reports, runs
from vic.api.auth import require_api_key
from vic.config import Settings, get_settings
from vic.errors import register_error_handlers
from vic.storage import get_repository

from vic.runner import get_manager

API_VERSION = "0.2.0"
logger = logging.getLogger("vic")


def check_production_settings(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    problems = []
    if not settings.api_shared_secret:
        problems.append("API_SHARED_SECRET must be set")
    if settings.dev_stubs:
        problems.append("DEV_STUBS must be false")
    if settings.run_backend != "pipeline":
        problems.append("RUN_BACKEND must be pipeline")
    if "*" in settings.cors_list:
        problems.append("CORS_ORIGINS must list explicit origins, not '*'")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    check_production_settings(settings)
    recovered = get_repository().startup()  # fails interrupted runs, then seeds fixtures
    app.state.recovered_runs = recovered
    if recovered:
        logger.warning("Marked %d interrupted run(s) as failed", recovered)
    yield
    await get_manager().shutdown()  # cancel running tasks; they record themselves as interrupted


def build_openapi(app: FastAPI) -> dict:
    """OpenAPI schema where 422 uses the shared error envelope instead of FastAPI's default."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes,
                         description="Contract v1.")
    components = schema.get("components", {}).get("schemas", {})
    ref = {"$ref": "#/components/schemas/ErrorEnvelope"}
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            responses = operation.get("responses", {})
            if "422" in responses:
                responses["422"] = {"description": "Validation error",
                                    "content": {"application/json": {"schema": ref}}}
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    app = FastAPI(title="Virtual Investment Committee API", version=API_VERSION, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-VIC-Mock"])
    register_error_handlers(app)
    app.include_router(health.router)  # /health stays open for platform health checks
    for module in (cases, runs, reports, evidence):
        app.include_router(module.router, dependencies=[Depends(require_api_key)])
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
