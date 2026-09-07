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

CREATE INDEX IF NOT EXISTS idx_notification_vn
ON notification_log(vn);

CREATE INDEX IF NOT EXISTS idx_notification_status
ON notification_log(status);

CREATE INDEX IF NOT EXISTS idx_notification_date
ON notification_log(queue_date);
