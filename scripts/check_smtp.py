import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from email_service import EmailDeliveryError, EmailService, verification_email


def main() -> int:
    to_email = os.getenv("EMAIL_TEST_TO") or os.getenv("EMAIL_FROM")
    if not to_email:
        print("Set EMAIL_TEST_TO or EMAIL_FROM before running this script.", file=sys.stderr)
        return 1

    service = EmailService()
    if not service.is_configured:
        print("Email API is not configured. Missing: " + ", ".join(service.config_errors), file=sys.stderr)
        return 1

    try:
        service.send_html(to_email, "Email API Test - Alrwad", verification_email("123456"))
    except EmailDeliveryError as exc:
        print(f"Email API test failed during {exc.phase}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Email API test failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Email API test email sent to {to_email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
