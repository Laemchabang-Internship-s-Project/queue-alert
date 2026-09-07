import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from app.postgres import (
    init_db,
    get_notification_stats,
    get_recent_notifications
)
from app.worker import queue_worker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    worker = asyncio.create_task(queue_worker())

    yield

    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="NEOQ → MOPH Alert",
    version="1.1.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "service": "NEOQ → MOPH Alert",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {
        "status": "ok"
    }


@app.get("/stats")
async def stats():
    """
    API สรุปสถิติการส่งแจ้งเตือนประจำวัน ( Dashboard Monitoring )
    """
    data = await get_notification_stats()
    return {
        "status": "ok",
        "data": data
    }


@app.get("/notifications")
async def notifications(limit: int = Query(default=50, ge=1, le=200)):
    """
    API ดูรายการแจ้งเตือนล่าสุด พร้อมรายละเอียดสถานะ MOPH Response และ Retry
    """
    items = await get_recent_notifications(limit=limit)
    return {
        "status": "ok",
        "count": len(items),
        "data": items
    }
