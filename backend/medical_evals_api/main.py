from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings, validate_runtime_security
from .routes import auth, catalog, evaluations, me, reports, results


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    validate_runtime_security(settings)
    yield


app = FastAPI(title="Medical Evals API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(me.router)
app.include_router(evaluations.router)
app.include_router(results.router)
app.include_router(reports.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
