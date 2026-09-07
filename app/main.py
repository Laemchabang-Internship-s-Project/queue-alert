import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.postgres import init_db
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
    version="1.0.0",
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
