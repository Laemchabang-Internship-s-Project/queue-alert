import aiomysql
from app.config import settings


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
            sql = """
                SELECT
                    q.vn,
                    q.hn,
                    q.room_code,
                    COALESCE(r.name, r.room_name, r.roomname, q.room_code) AS room_name,
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
            await cursor.execute(sql)
            return await cursor.fetchall()
    finally:
        conn.close()
