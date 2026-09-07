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
            # 1. Query โดย JOIN opd_queue กับ room ด้วย room_code และ room_name
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
                    q.status_open_vn
                FROM opd_queue q
                LEFT JOIN room r ON q.room_code = r.room_code
                WHERE q.date = CURDATE()
                  AND q.status_id = 1
                  AND q.qnumber IS NOT NULL
                ORDER BY q.time ASC, q.vn ASC
            """
            try:
                await cursor.execute(sql_join)
                return await cursor.fetchall()
            except Exception as exc:
                logger.warning("JOIN room table with r.room_name failed (%s), falling back to opd_queue only", exc)

            # 2. Fallback: Query เฉพาะ opd_queue กรณีตาราง room ไม่สามารถ JOIN ได้
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
                    status_open_vn
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
