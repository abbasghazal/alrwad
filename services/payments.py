from typing import Dict

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models


FINAL_TRANSACTION_STATUSES = {"approved", "completed"}
OPEN_BOOKING_STATUSES = {"pending", "confirmed"}


def wallet_balance(db: Session, user_id: int) -> float:
    total = db.query(func.coalesce(func.sum(models.WalletTransaction.amount), 0.0)).filter(
        models.WalletTransaction.user_id == user_id,
        models.WalletTransaction.is_deleted == False,
        models.WalletTransaction.status.in_(FINAL_TRANSACTION_STATUSES),
    ).scalar()
    return round(float(total or 0), 2)


def wallet_summary(db: Session, user_id: int) -> Dict[str, float]:
    pending = db.query(func.coalesce(func.sum(models.WalletTransaction.amount), 0.0)).filter(
        models.WalletTransaction.user_id == user_id,
        models.WalletTransaction.is_deleted == False,
        models.WalletTransaction.status == "pending",
    ).scalar()
    return {
        "balance": wallet_balance(db, user_id),
        "pending": round(float(pending or 0), 2),
    }


def ensure_positive_amount(amount: float) -> None:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="المبلغ يجب أن يكون أكبر من صفر")


def require_booking_payment_match(booking: models.TutorBooking, amount: float) -> None:
    ensure_positive_amount(amount)
    if round(float(amount), 2) != round(float(booking.price or 0), 2):
        raise HTTPException(status_code=400, detail="المبلغ لا يطابق سعر الحجز")
    if booking.status not in OPEN_BOOKING_STATUSES:
        raise HTTPException(status_code=400, detail="لا يمكن دفع حجز غير نشط")
    if booking.payment_status == "paid":
        raise HTTPException(status_code=400, detail="هذا الحجز مدفوع بالفعل")
