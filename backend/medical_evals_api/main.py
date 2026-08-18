from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import auth, catalog, evaluations, me, reports, results


app = FastAPI(title="Medical Evals API", version="0.1.0")
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
