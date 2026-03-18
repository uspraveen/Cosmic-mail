from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Cosmic Mail"
    api_prefix: str = "/v1"
    database_url: str = "sqlite:///./cosmic_mail.db"
    admin_api_key: str | None = None
    mail_engine_backend: str = "noop"
    james_webadmin_url: str = "http://127.0.0.1:8000"
    james_admin_token: str | None = None
    public_mail_hostname: str = "mx.cosmicmail.local"
    public_submission_hostname: str | None = None
    public_submission_port: int = 587
    public_submission_use_starttls: bool = True
    public_imap_hostname: str | None = None
    public_imap_port: int = 993
    public_imap_use_ssl: bool = True
    default_dkim_selector: str = "cosmic"
    default_mx_priority: int = 10
    default_dns_ttl: int = 3600
    dmarc_policy: str = "quarantine"
    dmarc_subdomain_policy: str = "quarantine"
    dmarc_rua: str | None = None
    default_mailbox_quota_mb: int = 1024
    default_mailbox_quota_messages: int = 100_000
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 25
    smtp_use_ssl: bool = False
    smtp_use_starttls: bool = False
    smtp_validate_certs: bool = True
    smtp_auth_enabled: bool = False
    smtp_timeout_seconds: float = 30.0
    imap_host: str = "127.0.0.1"
    imap_port: int = 993
    imap_use_ssl: bool = True
    imap_use_starttls: bool = False
    imap_validate_certs: bool = True
    imap_timeout_seconds: float = 30.0
    imap_inbox_folder: str = "INBOX"
    sync_worker_enabled: bool = False
    sync_worker_interval_seconds: int = 60
    sync_worker_batch_size: int = 100
    secret_key: str = "change-me-for-production"
    attachment_storage_path: str = "/data/attachments"
    max_attachment_size_mb: int = 25
    cors_allowed_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_prefix="COSMIC_MAIL_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
