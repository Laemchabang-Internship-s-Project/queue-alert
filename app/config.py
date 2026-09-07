from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =========================
    # NEOQ XP
    # =========================
    neoq_host: str = "192.168.10.253"
    neoq_user: str = "YOUR_NEOQ_USER"
    neoq_pass: str = "YOUR_NEOQ_PASSWORD"
    neoq_name: str = "neoq_xp"
    neoq_port: int = 3306

    # =========================
    # HOS
    # =========================
    hos_host: str = "192.168.10.10"
    hos_user: str = "YOUR_HOS_USER"
    hos_pass: str = "YOUR_HOS_PASSWORD"
    hos_name: str = "hos"
    hos_port: int = 3306

    # =========================
    # PostgreSQL
    # =========================
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "moph"
    postgres_password: str = "moph_password"
    postgres_db: str = "moph_alert"

    # =========================
    # MOPH
    # =========================
    moph_url: str = "https://morpromt2c.moph.go.th/alert/v3.1/template"
    moph_client_key: str = "YOUR_CLIENT_KEY"
    moph_secret_key: str = "YOUR_SECRET_KEY"
    moph_access_token: str = "YOUR_ACCESS_TOKEN"

    # =========================
    # Worker & Notifications
    # =========================
    poll_interval_seconds: int = 5
    request_timeout_seconds: int = 15
    almost_turn_threshold: int = 2  # แจ้งเตือนเมื่อเหลืออีก <= 2 คิว
    queue_tracking_url: str = ""   # URL ติดตามสถานะคิว (ถ้ามี)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
