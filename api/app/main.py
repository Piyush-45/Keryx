from fastapi import FastAPI

from app.routers import agent_configs

app = FastAPI(title="Voice Platform API", version="0.0.0")
app.include_router(agent_configs.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
