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
                response_status INTEGER,
                response_body TEXT,
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (vn, notification_type)
            );
        """)


async def create_notification(data):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO notification_log (
                vn,
                queue_date,
                queue_no,
                cid,
                patient_name,
                hn_no,
                service,
                notification_type
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            ON CONFLICT (vn, notification_type)
            DO NOTHING
            RETURNING id
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
        return row


async def update_notification(
    vn,
    notification_type,
    success,
    response_status,
    response_body
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE notification_log
            SET
                status = $1,
                attempt_count = attempt_count + 1,
                response_status = $2,
                response_body = $3,
                sent_at = CASE WHEN $4 THEN NOW() ELSE sent_at END,
                updated_at = NOW()
            WHERE vn = $5
              AND notification_type = $6
            """,
            "SENT" if success else "FAILED",
            response_status,
            response_body,
            success,
            vn,
            notification_type
        )
