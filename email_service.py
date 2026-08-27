from html import escape
import smtplib
from email.message import EmailMessage
from typing import Optional

import httpx

from app_settings import get_settings


class EmailDeliveryError(RuntimeError):
    def __init__(self, message: str, phase: str, original: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.phase = phase
        self.original = original


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return self.settings.email_configured

    @property
    def config_errors(self) -> list:
        errors = []
        if not self.settings.email_api_configured and not self.settings.smtp_configured:
            errors.append("EMAIL_API_* أو SMTP_*")
        return errors

    def check(self) -> bool:
        return self.is_configured

    def send_html(self, to_email: str, subject: str, html_body: str) -> None:
        if not self.is_configured:
            missing = ", ".join(self.config_errors) or "EMAIL_API settings"
            raise RuntimeError(f"Email API is not configured: {missing}")

        if self.settings.email_api_configured and "mailgun" in self.settings.email_api_url.lower():
            response = self._send_mailgun(to_email, subject, html_body)
        elif self.settings.email_api_configured:
            response = self._send_json_api(to_email, subject, html_body)
            if response.status_code >= 400:
                detail = _extract_detail(response)
                raise EmailDeliveryError(
                    f"Email API rejected the request: {response.status_code} {detail}",
                    "send",
                )
        else:
            self._send_smtp(to_email, subject, html_body)

    def _send_smtp(self, to_email: str, subject: str, html_body: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content("يرجى فتح الرسالة باستخدام بريد يدعم HTML.")
        message.add_alternative(html_body, subtype="html")

        smtp_class = smtplib.SMTP_SSL if self.settings.smtp_ssl else smtplib.SMTP
        try:
            with smtp_class(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.email_api_timeout) as server:
                if self.settings.smtp_tls and not self.settings.smtp_ssl:
                    server.starttls()
                server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(message)
        except Exception as exc:
            raise EmailDeliveryError(f"{type(exc).__name__}: {exc}", "send", exc) from exc

    def _send_json_api(self, to_email: str, subject: str, html_body: str) -> httpx.Response:
        payload = {
            "from": self.settings.email_from,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.email_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            return httpx.post(
                self.settings.email_api_url,
                headers=headers,
                json=payload,
                timeout=self.settings.email_api_timeout,
            )
        except Exception as exc:
            raise EmailDeliveryError(f"{type(exc).__name__}: {exc}", "connect", exc) from exc

    def _send_mailgun(self, to_email: str, subject: str, html_body: str) -> httpx.Response:
        data = {
            "from": self.settings.email_from,
            "to": to_email,
            "subject": subject,
            "html": html_body,
        }
        try:
            return httpx.post(
                self.settings.email_api_url,
                auth=("api", self.settings.email_api_key),
                data=data,
                timeout=self.settings.email_api_timeout,
            )
        except Exception as exc:
            raise EmailDeliveryError(f"{type(exc).__name__}: {exc}", "connect", exc) from exc


def _extract_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text.strip() or response.reason_phrase

    if isinstance(data, dict):
        for key in ("message", "error", "detail"):
            value = data.get(key)
            if value:
                return str(value)
    return str(data)


def reset_password_email(code: str) -> str:
    safe_code = escape(code)
    return f"""
    <html lang="ar" dir="rtl">
      <body style="font-family: Arial, sans-serif; line-height: 1.8;">
        <h2>استعادة كلمة المرور</h2>
        <p>مرحباً،</p>
        <p>تم طلب إعادة تعيين كلمة المرور الخاصة بحسابك.</p>
        <p>رمز التحقق:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px;">{safe_code}</p>
        <p>صلاحية الرمز: 10 دقائق</p>
        <p>إذا لم تطلب ذلك تجاهل الرسالة.</p>
      </body>
    </html>
    """


def verification_email(code: str) -> str:
    safe_code = escape(code)
    return f"""
    <html lang="ar" dir="rtl">
      <body style="font-family: Arial, sans-serif; line-height: 1.8;">
        <h2>تفعيل البريد الإلكتروني</h2>
        <p>مرحباً،</p>
        <p>استخدم الرمز التالي لتفعيل حسابك:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px;">{safe_code}</p>
        <p>صلاحية الرمز: 10 دقائق</p>
      </body>
    </html>
    """
