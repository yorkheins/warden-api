import time

from fastapi import APIRouter

router = APIRouter()
_start = time.monotonic()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": round(time.monotonic() - _start, 2),
    }
