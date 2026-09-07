import asyncio
import logging

from app.config import settings
from app.neoq import get_waiting_queues
from app.moph import (
    build_payload,
    build_queue_with_url_payload,
    build_almost_turn_payload,
    build_welcome_payload,
    build_queue_changed_payload,
    build_queue_changed_with_url_payload,
    send_to_moph
)
from app.postgres import (
    sync_queues_to_postgres,
    get_pending_queues_from_postgres,
    get_almost_turn_queues_from_postgres,
    get_welcome_queues_from_postgres,
    get_changed_queues_from_postgres,
    clear_queue_changed_flag,
    record_notification_start,
    update_notification_result
)

logger = logging.getLogger(__name__)


async def process_queue_row(row, notification_type: str = "queue_created"):
    """
    ประมวลผลการยิงแจ้งเตือนคิว MOPH (รองรับทั้ง queue_created และ almost_turn)
    """
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

    room_display = row.get("room_name") or row.get("room_code") or ""
    service = (
        f'{row.get("category_name") or ""} '
        f'ห้อง {room_display}'
    ).strip()

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

    # 2. สร้าง MOPH JSON Payload ตามประเภทการแจ้งเตือน
    if notification_type == "welcome":
        payload = build_welcome_payload(row)
    elif notification_type.startswith("almost_turn"):
        queue_waiting = row.get("queue_waiting", 0)
        payload = build_almost_turn_payload(
            row=row,
            queue_waiting=queue_waiting,
            url=settings.queue_tracking_url
        )
    elif notification_type == "queue_changed":
        queue_waiting = row.get("queue_waiting", 0)
        if settings.queue_tracking_url:
            payload = build_queue_changed_with_url_payload(
                row=row,
                queue_waiting=queue_waiting,
                url=settings.queue_tracking_url
            )
        else:
            payload = build_queue_changed_payload(
                row=row,
                queue_waiting=queue_waiting
            )
    else:
        # queue_created
        if settings.queue_tracking_url:
            payload = build_queue_with_url_payload(
                row=row,
                url=settings.queue_tracking_url
            )
        else:
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
        logger.info(
            "MOPH SENT SUCCESS [%s] VN=%s queue=%s cid=%s payload=%s res=%s",
            notification_type, vn, queue_no, row.get("cid"), payload, res_text
        )
        if notification_type == "queue_changed":
            await clear_queue_changed_flag(vn)
    else:
        if is_permanent_error:
            logger.error(
                "MOPH PERMANENT FAILED [%s] VN=%s http=%s moph_code=%s res=%s",
                notification_type, vn, http_status, moph_code, res_text[:500]
            )
        else:
            attempt = row.get("attempt_count", 0) + 1
            max_r = row.get("max_retries", 3)
            logger.warning(
                "MOPH RETRYABLE FAILED (Attempt %d/%d) [%s] VN=%s http=%s moph_code=%s res=%s",
                attempt, max_r, notification_type, vn, http_status, moph_code, res_text[:500]
            )


async def queue_worker():
    logger.info(
        "NEOQ MOPH Worker started (Sync + Queue Created + Almost Turn Notifications Enabled)"
    )

    while True:
        try:
            # Phase A: Sync ข้อมูลจาก NEOQ มาพักไว้ที่ Local Postgres (ลด Workload NEOQ หลัก)
            neoq_rows = await get_waiting_queues()
            if neoq_rows:
                await sync_queues_to_postgres(neoq_rows)
                logger.info("Synced %d waiting queues from NEOQ to Local Postgres", len(neoq_rows))

            # Phase B0: ประมวลผลแจ้งเตือนแรกเริ่ม (welcome)
            welcome_rows = await get_welcome_queues_from_postgres()
            if welcome_rows:
                logger.info("Processing %d pending/retry 'welcome' notifications", len(welcome_rows))
                for row in welcome_rows:
                    await process_queue_row(row, notification_type="welcome")

            # Phase B1: ประมวลผลแจ้งเตือนคิวแรกรับ (queue_created)
            created_rows = await get_pending_queues_from_postgres()
            if created_rows:
                logger.info("Processing %d pending/retry 'queue_created' notifications", len(created_rows))
                for row in created_rows:
                    await process_queue_row(row, notification_type="queue_created")

            # Phase B2: ประมวลผลแจ้งเตือนใกล้ถึงคิว (almost_turn: ส่งทั้งตอนเหลือ 2 คิว และ 1 คิว)
            for target_waiting in [2, 1]:
                almost_rows = await get_almost_turn_queues_from_postgres(
                    target_waiting=target_waiting
                )
                if almost_rows:
                    logger.info("Processing %d pending/retry 'almost_turn_%d' notifications", len(almost_rows), target_waiting)
                    for row in almost_rows:
                        await process_queue_row(row, notification_type=f"almost_turn_{target_waiting}")

            # Phase B3: ประมวลผลแจ้งเตือนเปลี่ยนแปลงคิว (queue_changed)
            changed_rows = await get_changed_queues_from_postgres()
            if changed_rows:
                logger.info("Processing %d pending/retry 'queue_changed' notifications", len(changed_rows))
                for row in changed_rows:
                    await process_queue_row(row, notification_type="queue_changed")

        except Exception:
            logger.exception("Worker execution error in sync/processing cycle")

        await asyncio.sleep(settings.poll_interval_seconds)
