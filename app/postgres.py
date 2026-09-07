import asyncpg
from app.config import settings

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_db,
            min_size=1,
            max_size=10
        )
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # สร้าง Sync table สำหรับลดภาระ NEOQ
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS opd_queue_sync (
                vn VARCHAR(50) PRIMARY KEY,
                hn VARCHAR(50),
                cid VARCHAR(13),
                pname VARCHAR(50),
                fname VARCHAR(100),
                lname VARCHAR(100),
                qnumber VARCHAR(50),
                category_name VARCHAR(100),
                room_code VARCHAR(50),
                room_name VARCHAR(150),
                queue_date DATE,
                queue_time TIME,
                status_id INTEGER,
                synced_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_queue_sync_status ON opd_queue_sync(queue_date, status_id);
        """)

        # สร้าง Notification log table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                id BIGSERIAL PRIMARY KEY,
                vn VARCHAR(50) NOT NULL,
                queue_date DATE NOT NULL,
                queue_no VARCHAR(50) NOT NULL,
                cid VARCHAR(13),
                patient_name TEXT,
                hn_no VARCHAR(50),
                service TEXT,
                notification_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                is_permanent_error BOOLEAN NOT NULL DEFAULT FALSE,
                response_status INTEGER,
                moph_code VARCHAR(50),
                response_body TEXT,
                last_error TEXT,
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (vn, notification_type)
            );
            CREATE INDEX IF NOT EXISTS idx_notification_vn ON notification_log(vn);
            CREATE INDEX IF NOT EXISTS idx_notification_status ON notification_log(status);
            CREATE INDEX IF NOT EXISTS idx_notification_date ON notification_log(queue_date);
        """)


async def sync_queues_to_postgres(rows):
    """
    UPSERT ข้อมูลคิวจาก NEOQ ลงใน Local PostgreSQL
    เพื่อลด Workload ของ NEOQ Database หลัก
    """
    if not rows:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        sql = """
            INSERT INTO opd_queue_sync (
                vn, hn, cid, pname, fname, lname,
                qnumber, category_name, room_code, room_name,
                queue_date, queue_time, status_id, synced_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12, $13, NOW()
            )
            ON CONFLICT (vn) DO UPDATE SET
                hn = EXCLUDED.hn,
                cid = EXCLUDED.cid,
                pname = EXCLUDED.pname,
                fname = EXCLUDED.fname,
                lname = EXCLUDED.lname,
                qnumber = EXCLUDED.qnumber,
                category_name = EXCLUDED.category_name,
                room_code = EXCLUDED.room_code,
                room_name = EXCLUDED.room_name,
                queue_date = EXCLUDED.queue_date,
                queue_time = EXCLUDED.queue_time,
                status_id = EXCLUDED.status_id,
                synced_at = NOW();
        """
        records = [
            (
                str(r["vn"]),
                str(r["hn"]) if r.get("hn") else None,
                str(r["cid"]) if r.get("cid") else None,
                r.get("pname"),
                r.get("fname"),
                r.get("lname"),
                str(r["qnumber"]) if r.get("qnumber") is not None else None,
                r.get("category_name"),
                r.get("room_code"),
                r.get("room_name"),
                r.get("date"),
                r.get("time"),
                r.get("status_id")
            )
            for r in rows
        ]
        await conn.executemany(sql, records)


async def get_pending_queues_from_postgres():
    """
    ดึงรายการคิวใหม่ที่ยังไม่เคยส่งแจ้งเตือนแรกรับ (queue_created)
    หรือเคยส่งล้มเหลวแต่ยัง Retry ได้
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                s.vn, s.hn, s.cid, s.pname, s.fname, s.lname,
                s.qnumber, s.category_name, s.room_code, s.room_name,
                s.queue_date AS date, s.queue_time AS time, s.status_id,
                COALESCE(l.status, 'PENDING') AS notif_status,
                COALESCE(l.attempt_count, 0) AS attempt_count,
                COALESCE(l.max_retries, 3) AS max_retries
            FROM opd_queue_sync s
            LEFT JOIN notification_log l
                   ON s.vn = l.vn AND l.notification_type = 'queue_created'
            WHERE s.queue_date = CURRENT_DATE
              AND s.status_id = 1
              AND s.qnumber IS NOT NULL
              AND (
                  l.vn IS NULL
                  OR (l.status = 'FAILED' AND l.attempt_count < l.max_retries AND l.is_permanent_error = FALSE)
              )
            ORDER BY s.queue_time ASC, s.vn ASC;
        """)
        return [dict(r) for r in rows]


async def get_almost_turn_queues_from_postgres(threshold: int = 2):
    """
    ดึงรายการคิวที่ใกล้ถึงคิว (queue_waiting <= threshold)
    ที่ยังไม่เคยส่งแจ้งเตือนประเภท almost_turn หรือเคยส่งล้มเหลวแต่ยัง Retry ได้
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH queue_positions AS (
                SELECT
                    s.vn, s.hn, s.cid, s.pname, s.fname, s.lname,
                    s.qnumber, s.category_name, s.room_code, s.room_name,
                    s.queue_date AS date, s.queue_time AS time, s.status_id,
                    (
                        COUNT(*) OVER (
                            PARTITION BY s.queue_date, COALESCE(s.room_code, s.room_name)
                            ORDER BY s.queue_time ASC, s.vn ASC
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                        )
                    ) AS queue_waiting
                FROM opd_queue_sync s
                WHERE s.queue_date = CURRENT_DATE
                  AND s.status_id = 1
                  AND s.qnumber IS NOT NULL
            )
            SELECT
                q.*,
                COALESCE(l.status, 'PENDING') AS notif_status,
                COALESCE(l.attempt_count, 0) AS attempt_count,
                COALESCE(l.max_retries, 3) AS max_retries
            FROM queue_positions q
            LEFT JOIN notification_log l
                   ON q.vn = l.vn AND l.notification_type = 'almost_turn'
            WHERE q.queue_waiting <= $1
              AND (
                  l.vn IS NULL
                  OR (l.status = 'FAILED' AND l.attempt_count < l.max_retries AND l.is_permanent_error = FALSE)
              )
            ORDER BY q.queue_waiting ASC, q.time ASC;
        """, threshold)
        return [dict(r) for r in rows]


async def record_notification_start(data):
    """
    บันทึกการเริ่มส่งใน notification_log ( status = 'PROCESSING' )
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO notification_log (
                vn, queue_date, queue_no, cid,
                patient_name, hn_no, service, notification_type, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'PROCESSING')
            ON CONFLICT (vn, notification_type)
            DO UPDATE SET
                status = 'PROCESSING',
                updated_at = NOW()
            RETURNING id;
            """,
            data["vn"],
            data["queue_date"],
            data["queue_no"],
            data["cid"],
            data["patient_name"],
            data["hn_no"],
            data["service"],
            data["notification_type"]
        )


async def update_notification_result(
    vn,
    notification_type,
    success,
    is_permanent_error,
    response_status,
    moph_code,
    response_body
):
    """
    อัปเดตผลลัพธ์การส่ง MOPH ลง notification_log (SENT หรือ FAILED)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        status_str = "SENT" if success else "FAILED"
        body_text = response_body[:10000] if response_body else None
        await conn.execute(
            """
            UPDATE notification_log
            SET
                status = $1,
                attempt_count = attempt_count + 1,
                is_permanent_error = $2,
                response_status = $3,
                moph_code = $4,
                response_body = $5,
                last_error = CASE WHEN $6 THEN NULL ELSE $5 END,
                sent_at = CASE WHEN $6 THEN NOW() ELSE sent_at END,
                updated_at = NOW()
            WHERE vn = $7
              AND notification_type = $8
            """,
            status_str,
            is_permanent_error,
            response_status,
            moph_code,
            body_text,
            success,
            vn,
            notification_type
        )


async def get_notification_stats():
    """
    ดึงสรุปสถิติการส่งแจ้งเตือนประจำวัน (สำหรับ Monitoring Dashboard)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE) AS total_today,
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE AND notification_type = 'queue_created') AS created_count,
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE AND notification_type = 'almost_turn') AS almost_turn_count,
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE AND status = 'SENT') AS sent_count,
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE AND status = 'PROCESSING') AS processing_count,
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE AND status = 'FAILED') AS failed_count,
                COUNT(*) FILTER (WHERE queue_date = CURRENT_DATE AND is_permanent_error = TRUE) AS permanent_failed_count
            FROM notification_log;
        """)
        return dict(row) if row else {}


async def get_recent_notifications(limit: int = 50):
    """
    ดึงรายการแจ้งเตือนล่าสุดเพื่อดูรายละเอียดใน Monitoring Dashboard
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                vn, queue_date, queue_no, cid, patient_name, hn_no, service,
                notification_type, status, attempt_count, max_retries,
                is_permanent_error, response_status, moph_code, last_error,
                sent_at, created_at, updated_at
            FROM notification_log
            ORDER BY updated_at DESC
            LIMIT $1;
        """, limit)
        return [dict(r) for r in rows]
