from html import escape
from typing import Optional

from sqlalchemy.orm import Session

import models
from email_service import EmailService


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str,
    send_email: bool = False,
) -> models.Notification:
    notification = models.Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
    )
    db.add(notification)
    if send_email:
        user: Optional[models.User] = db.query(models.User).filter(models.User.id == user_id).first()
        email_service = EmailService()
        if user and user.email and email_service.is_configured:
            try:
                email_service.send_html(
                    user.email,
                    title,
                    _simple_email(title, message),
                )
            except Exception as exc:
                print(f"[EMAIL] Failed to send notification email to {user.email}: {exc}")
    return notification


def _simple_email(title: str, message: str) -> str:
    return f"""
    <html lang="ar" dir="rtl">
      <body style="font-family: Arial, sans-serif; line-height: 1.8;">
        <h2>{escape(title)}</h2>
        <p>{escape(message)}</p>
      </body>
    </html>
    """
