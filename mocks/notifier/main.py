import asyncio
import os
import random
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Notifier")

ERROR_RATE  = float(os.getenv("MOCK_ERROR_RATE", "0.0"))
LATENCY_MIN = int(os.getenv("MOCK_LATENCY_MS_MIN", "100"))
LATENCY_MAX = int(os.getenv("MOCK_LATENCY_MS_MAX", "500"))

_received: list[dict] = []


@app.post("/notify/oncall")
async def notify_oncall(request: Request):
    body = await request.json()
    await asyncio.sleep(random.randint(LATENCY_MIN, LATENCY_MAX) / 1000)

    if random.random() < ERROR_RATE:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "mock notifier error"},
        )

    record = {**body, "received_at": datetime.now(timezone.utc).isoformat()}
    _received.append(record)
    return {"success": True, "message": "on-call notified"}


@app.get("/notify/received")
async def get_received():
    return {"count": len(_received), "notifications": _received}


@app.delete("/notify/received")
async def clear_received():
    _received.clear()
    return {"message": "cleared"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-notifier"}
