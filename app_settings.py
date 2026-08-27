import os
from functools import lru_cache
from typing import List

from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        self.database_url = self._required("DATABASE_URL")
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql://", 1)
        if self.database_url.startswith("sqlite"):
            raise RuntimeError("SQLite is not allowed. Set DATABASE_URL to a PostgreSQL URL.")

        self.jwt_secret_key = self._required("JWT_SECRET_KEY")
        self.cors_origins = self._cors_origins()

        self.email_api_url = self._clean(os.getenv("EMAIL_API_URL", ""))
        self.email_api_key = self._clean(os.getenv("EMAIL_API_KEY"), remove_spaces=True)
        self.email_from = self._clean(os.getenv("EMAIL_FROM", ""))
        self.email_api_timeout = int(os.getenv("EMAIL_API_TIMEOUT", "15"))
        self.smtp_host = self._clean(os.getenv("SMTP_HOST", ""))
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = self._clean(os.getenv("SMTP_USERNAME", ""))
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from_email = self._clean(os.getenv("SMTP_FROM_EMAIL", ""))
        self.smtp_tls = os.getenv("SMTP_TLS", "true").lower() == "true"
        self.smtp_ssl = os.getenv("SMTP_SSL", "false").lower() == "true"

        self.upload_root = os.getenv("UPLOAD_ROOT", "static/uploads").rstrip("/")
        self.upload_url_prefix = os.getenv("UPLOAD_URL_PREFIX", "/uploads").rstrip("/")
        self.storage_backend = os.getenv("STORAGE_BACKEND", "local").lower()
        self.storage_public_base_url = self._clean(os.getenv("STORAGE_PUBLIC_BASE_URL", ""))

        self.payment_webhook_secret = self._clean(os.getenv("PAYMENT_WEBHOOK_SECRET", ""))

        self.default_owner_username = os.getenv("DEFAULT_OWNER_USERNAME", "admin").lower()
        self.default_owner_email = os.getenv("DEFAULT_OWNER_EMAIL", "admin@alrwad.edu").lower()
        self.default_owner_password = os.getenv("DEFAULT_OWNER_PASSWORD")

    def _required(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"{name} is required")
        return value

    def _clean(self, value: str, remove_spaces: bool = False) -> str:
        if not value:
            return value
        value = value.strip().strip('"').strip("'")
        if remove_spaces:
            value = value.replace(" ", "")
        return value

    def _cors_origins(self) -> List[str]:
        origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
        if self.environment == "production":
            if not origins:
                raise RuntimeError("CORS_ORIGINS is required in production")
            if "*" in origins:
                raise RuntimeError('CORS_ORIGINS cannot contain "*" in production')
        else:
            origins.extend(
                [
                    "http://localhost",
                    "http://localhost:3000",
                    "http://localhost:5173",
                    "http://127.0.0.1:3000",
                    "http://127.0.0.1:5173",
                ]
            )
        return sorted(set(origins))

    @property
    def email_configured(self) -> bool:
        return bool(self.email_api_configured or self.smtp_configured)

    @property
    def email_api_configured(self) -> bool:
        return bool(self.email_api_url and self.email_api_key and self.email_from)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and self.smtp_from_email)


@lru_cache
def get_settings() -> Settings:
    return Settings()
