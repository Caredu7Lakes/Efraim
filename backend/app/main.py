from __future__ import annotations

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.buscas import router as buscas_router

app = FastAPI(title="Efraim", version="0.1.0")
app.include_router(auth_router)
app.include_router(buscas_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "servico": "efraim"}
