import asyncio
import os
import random

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Orchestrator")

ERROR_RATE  = float(os.getenv("MOCK_ERROR_RATE", "0.0"))
LATENCY_MIN = int(os.getenv("MOCK_LATENCY_MS_MIN", "100"))
LATENCY_MAX = int(os.getenv("MOCK_LATENCY_MS_MAX", "500"))


async def _simulate() -> bool:
    await asyncio.sleep(random.randint(LATENCY_MIN, LATENCY_MAX) / 1000)
    return random.random() < ERROR_RATE


async def _handle(action: str, request: Request) -> JSONResponse:
    body = await request.json()
    failed = await _simulate()
    if failed:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"mock error during {action}"},
        )
    return JSONResponse(
        content={
            "success": True,
            "message": f"{action} executed",
            "project_id": body.get("project_id"),
            "environment_id": body.get("environment_id"),
        }
    )


@app.post("/rollback")
async def rollback(request: Request):
    return await _handle("rollback", request)


@app.post("/restart")
async def restart(request: Request):
    return await _handle("restart", request)


@app.post("/scale")
async def scale(request: Request):
    return await _handle("scale_up", request)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-orchestrator"}
