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
                    vn,
                    hn,
                    room_code,
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
            await cursor.execute(sql)
            return await cursor.fetchall()
    finally:
        conn.close()
