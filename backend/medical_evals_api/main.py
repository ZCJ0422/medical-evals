from fastapi import FastAPI

from .routes import auth, evaluations, me


app = FastAPI(title="Medical Evals API", version="0.1.0")
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(evaluations.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
