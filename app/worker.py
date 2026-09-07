import asyncio
import logging

from app.config import settings
from app.neoq import get_waiting_queues
from app.moph import build_payload, send_to_moph
from app.postgres import (
    sync_queues_to_postgres,
    get_pending_queues_from_postgres,
    record_notification_start,
    update_notification_result
)

logger = logging.getLogger(__name__)


async def process_queue_row(row):
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
        "cid": str(row["cid"]) if row.get("cid") else None,
        "patient_name": name,
        "hn_no": str(row["hn"]),
        "service": service,
        "notification_type": notification_type
    }

    # 1. บันทึกสถานะเริ่มประมวลผลใน Postgres
    await record_notification_start(data)

    # 2. สร้าง MOPH JSON Payload
    payload = build_payload(row)

    # 3. ยิง MOPH API และตรวจสอบทั้ง HTTP Code & JSON Body message_code
    is_success, is_permanent_error, http_status, moph_code, res_text = await send_to_moph(payload)

    # 4. อัปเดต Log ใน Postgres
    await update_notification_result(
        vn=vn,
        notification_type=notification_type,
        success=is_success,
        is_permanent_error=is_permanent_error,
        response_status=http_status,
        moph_code=moph_code,
        response_body=res_text
    )

    if is_success:
        logger.info("MOPH SENT SUCCESS VN=%s queue=%s", vn, queue_no)
    else:
        if is_permanent_error:
            logger.error(
                "MOPH PERMANENT FAILED VN=%s http=%s moph_code=%s res=%s",
                vn, http_status, moph_code, res_text[:200]
            )
        else:
            attempt = row.get("attempt_count", 0) + 1
            max_r = row.get("max_retries", 3)
            logger.warning(
                "MOPH RETRYABLE FAILED (Attempt %d/%d) VN=%s http=%s moph_code=%s",
                attempt, max_r, vn, http_status, moph_code
            )


async def queue_worker():
    logger.info("NEOQ MOPH Worker started (With Postgres Local Sync & MOPH Response Validation)")

    while True:
        try:
            # Phase A: Sync ข้อมูลจาก NEOQ มาพักไว้ที่ Local Postgres (ลด Workload NEOQ หลัก)
            neoq_rows = await get_waiting_queues()
            if neoq_rows:
                await sync_queues_to_postgres(neoq_rows)
                logger.info("Synced %d waiting queues from NEOQ to Local Postgres", len(neoq_rows))

            # Phase B: อ่านและส่งแจ้งเตือนจาก Local Postgres (Deduplication + Retry logic)
            pending_rows = await get_pending_queues_from_postgres()
            if pending_rows:
                logger.info("Processing %d pending/retry queue notifications", len(pending_rows))
                for row in pending_rows:
                    await process_queue_row(row)

        except Exception:
            logger.exception("Worker execution error in sync/processing cycle")

        await asyncio.sleep(settings.poll_interval_seconds)
