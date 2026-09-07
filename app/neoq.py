import aiomysql
import logging
from app.config import settings

logger = logging.getLogger(__name__)


async def get_waiting_queues():
    conn = await aiomysql.connect(
        host=settings.neoq_host,
        port=settings.neoq_port,
        user=settings.neoq_user,
        password=settings.neoq_pass,
        db=settings.neoq_name,
        autocommit=True
    )

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 1. Query โดย UNION ALL ระหว่าง opd_queue และ pharmacy_queue
            sql_join = """
                SELECT
                    q.vn,
                    q.hn,
                    q.room_code,
                    COALESCE(r.room_name, q.room_code) AS room_name,
                    q.category_name,
                    q.qnumber,
                    q.cid,
                    q.pname,
                    q.fname,
                    q.lname,
                    q.date,
                    q.time,
                    q.visit_time,
                    q.status_id,
                    q.status_open_vn,
                    'opd' AS queue_type
                FROM opd_queue q
                LEFT JOIN room r ON q.room_code = r.room_code
                WHERE q.date = CURDATE()
                  AND q.status_id = 1
                  AND q.qnumber IS NOT NULL

                UNION ALL

                SELECT
                    pq.vn,
                    pq.hn,
                    pq.room_code,
                    COALESCE(r.room_name, pq.room_code) AS room_name,
                    pq.category_name,
                    pq.qnumber,
                    pq.cid,
                    pq.pname,
                    pq.fname,
                    pq.lname,
                    pq.date,
                    pq.time,
                    pq.visit_time,
                    pq.status_id,
                    pq.status_open_vn,
                    'pharmacy' AS queue_type
                FROM pharmacy_queue pq
                LEFT JOIN room r ON pq.room_code = r.room_code
                WHERE pq.date = CURDATE()
                  AND (pq.status_id IN (1, 3) OR (COALESCE(pq.status_pharmacy, 0) IN (1, 3)))
                  AND pq.qnumber IS NOT NULL
                ORDER BY time ASC, vn ASC
            """
            try:
                await cursor.execute(sql_join)
                return await cursor.fetchall()
            except Exception as exc:
                logger.warning("UNION query with pharmacy_queue / room failed (%s), falling back to opd_queue", exc)

            # 2. Fallback: Query เฉพาะ opd_queue
            sql_fallback = """
                SELECT
                    vn,
                    hn,
                    room_code,
                    room_code AS room_name,
                    category_name,
                    qnumber,
                    cid,
                    pname,
                    fname,
                    lname,
                    date,
                    time,
                    visit_time,
                    status_id,
                    status_open_vn,
                    'opd' AS queue_type
                FROM opd_queue
                WHERE date = CURDATE()
                  AND status_id = 1
                  AND qnumber IS NOT NULL
                ORDER BY time ASC, vn ASC
            """
            await cursor.execute(sql_fallback)
            return await cursor.fetchall()

    finally:
        conn.close()
