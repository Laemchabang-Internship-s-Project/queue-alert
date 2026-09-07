-- ตาราง Local Sync สำหรับพักข้อมูลคิวจาก NEOQ (ลด Workload ของ NEOQ DB หลัก)
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

-- ตาราง Log การส่งแจ้งเตือน MOPH พร้อมรองรับ Deduplication และ Retry Tracking
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
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, PROCESSING, SENT, FAILED
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
