from fastapi import FastAPI

app = FastAPI(title="Voice Platform API", version="0.0.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
