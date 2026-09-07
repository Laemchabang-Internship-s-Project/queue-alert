import asyncio
import logging

from app.config import settings
from app.neoq import get_waiting_queues
from app.moph import build_payload, send_to_moph
from app.postgres import (
    create_notification,
    update_notification
)

logger = logging.getLogger(__name__)


async def process_queue(row):
    vn = str(row["vn"])
    queue_no = str(row["qnumber"])

    name = " ".join(
        str(x).strip()
        for x in [
            row.get("pname"),
            row.get("fname"),
            row.get("lname")
        ]
        if x
    )

    service = (
        f'{row.get("category_name") or ""} '
        f'ห้อง {row.get("room_code") or ""}'
    ).strip()

    notification_type = "queue_created"

    data = {
        "vn": vn,
        "queue_date": row["date"],
        "queue_no": queue_no,
        "cid": str(row["cid"]) if row["cid"] else None,
        "patient_name": name,
        "hn_no": str(row["hn"]),
        "service": service,
        "notification_type": notification_type
    }

    # =========================
    # กันส่งซ้ำ
    # =========================
    inserted = await create_notification(data)

    if inserted is None:
        logger.info(
            "Already sent VN=%s queue=%s",
            vn,
            queue_no
        )
        return

    # =========================
    # สร้าง MOPH JSON
    # =========================
    payload = build_payload(row)

    try:
        status_code, body, success = await send_to_moph(payload)

        await update_notification(
            vn,
            notification_type,
            success,
            status_code,
            body[:10000]
        )

        if success:
            logger.info(
                "MOPH SENT VN=%s queue=%s",
                vn,
                queue_no
            )
        else:
            logger.error(
                "MOPH FAILED VN=%s status=%s",
                vn,
                status_code
            )

    except Exception as e:
        logger.exception(
            "MOPH ERROR VN=%s",
            vn
        )

        await update_notification(
            vn,
            notification_type,
            False,
            None,
            str(e)
        )


async def queue_worker():
    logger.info("NEOQ MOPH Worker started")

    while True:
        try:
            rows = await get_waiting_queues()
            logger.info("Found %d waiting queues", len(rows))

            for row in rows:
                await process_queue(row)

        except Exception:
            logger.exception("Worker error")

        await asyncio.sleep(settings.poll_interval_seconds)
