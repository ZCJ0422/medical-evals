from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings, validate_runtime_security
from .database import get_engine
from .routes import auth, catalog, evaluations, models, monitoring, reports, results
from .schemas.common import ApiError, ApiErrorEnvelope


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    validate_runtime_security(settings)
    yield


def _uses_v1_error_envelope(request: Request) -> bool:
    return request.url.path.startswith("/api/v1/")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    payload = ApiErrorEnvelope(
        error={
            "code": code,
            "message": message,
            "request_id": _request_id(request),
        }
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers={"X-Request-ID": _request_id(request)},
    )


def _http_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "invalid_request",
    }.get(status_code, "request_error")


app = FastAPI(title="Medical Evals API", version="0.1.0", lifespan=lifespan)
logger = logging.getLogger("medical_evals_api.request")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = _request_id(request)
    logger.info("request_complete", extra={"request_id": _request_id(request), "method": request.method, "path": request.url.path, "status_code": response.status_code})
    return response


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    if _uses_v1_error_envelope(request):
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
        headers={"X-Request-ID": _request_id(request)},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    if _uses_v1_error_envelope(request):
        return _error_response(
            request,
            status_code=422,
            code="invalid_request",
            message=str(exc.errors()[0]["msg"]) if exc.errors() else "Invalid request",
        )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers={"X-Request-ID": _request_id(request)},
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    if _uses_v1_error_envelope(request):
        detail = exc.detail
        if isinstance(detail, list):
            message = "; ".join(str(item) for item in detail)
        else:
            message = str(detail)
        return _error_response(
            request,
            status_code=exc.status_code,
            code=_http_error_code(exc.status_code),
            message=message,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"X-Request-ID": _request_id(request)},
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, _exc: Exception):
    if _uses_v1_error_envelope(request):
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="Internal server error",
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"X-Request-ID": _request_id(request)},
    )


app.include_router(auth.router)
app.include_router(auth.v1_router)
app.include_router(auth.me_router)
app.include_router(auth.v1_me_router)
app.include_router(catalog.router)
app.include_router(catalog.v1_router)
app.include_router(evaluations.router)
app.include_router(evaluations.v1_router)
app.include_router(models.router)
app.include_router(results.router)
app.include_router(results.v1_router)
app.include_router(reports.router)
app.include_router(reports.v1_router)
app.include_router(monitoring.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    try:
        with get_engine(settings).connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return JSONResponse(content={"status": "ready", "database": "ok"})
