import os
import sys


REQUIRED = {
    "DATABASE_URL": "PostgreSQL connection string from Render",
    "JWT_SECRET_KEY": "long random secret",
    "CORS_ORIGINS": "public service URL, for example https://alroad.onrender.com",
}

OPTIONAL_WARN = {
    "EMAIL_API_URL": "email sending is disabled without an email API",
    "EMAIL_API_KEY": "email sending is disabled without an email API",
    "EMAIL_FROM": "email sending is disabled without an email API",
    "DEFAULT_OWNER_PASSWORD": "default admin user will not be created automatically",
}


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "..." + value[-4:]


def main() -> int:
    missing = [key for key in REQUIRED if not os.getenv(key)]
    if missing:
        print("[RENDER ENV] Missing required environment variables:", file=sys.stderr)
        for key in missing:
            print(f"  - {key}: {REQUIRED[key]}", file=sys.stderr)
        return 1

    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("sqlite"):
        print("[RENDER ENV] DATABASE_URL must be PostgreSQL, not SQLite.", file=sys.stderr)
        return 1

    print("[RENDER ENV] Required variables are present.")
    print(f"[RENDER ENV] DATABASE_URL={masked(database_url)}")
    print(f"[RENDER ENV] CORS_ORIGINS={os.getenv('CORS_ORIGINS')}")

    missing_optional = [key for key in OPTIONAL_WARN if not os.getenv(key)]
    for key in missing_optional:
        print(f"[RENDER ENV] Warning: {key} is not set; {OPTIONAL_WARN[key]}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
