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
            # 1. ลอง Query โดย JOIN ตาราง room เพื่อเอา room_name
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
                logger.warning("JOIN room table with r.room_name failed (%s), trying r.name...", exc)

            # 2. ลอง Query กรณีตาราง room ใช้ชื่อคอลัมน์ r.name
            sql_join_name = """
                SELECT
                    q.vn,
                    q.hn,
                    q.room_code,
                    COALESCE(r.name, q.room_code) AS room_name,
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
                LEFT JOIN room r ON q.room_code = r.room_code OR q.room_code = r.code
                WHERE q.date = CURDATE()
                  AND q.status_id = 1
                  AND q.qnumber IS NOT NULL
                ORDER BY q.time ASC, q.vn ASC
            """
            try:
                await cursor.execute(sql_join_name)
                return await cursor.fetchall()
            except Exception as exc:
                logger.warning("JOIN room table failed (%s), falling back to opd_queue table only", exc)

            # 3. Fallback หลัก: Query เฉพาะ opd_queue และใช้ room_code แทน room_name
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
