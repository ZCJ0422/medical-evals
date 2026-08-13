from fastapi import FastAPI

from .routes import auth, evaluations, me, reports, results


app = FastAPI(title="Medical Evals API", version="0.1.0")
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(evaluations.router)
app.include_router(results.router)
app.include_router(reports.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
