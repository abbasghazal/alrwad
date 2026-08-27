import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

import auth
import models
import schemas
from app_settings import get_settings
from database import get_db
from permissions.dependencies import require
from services.iraqi_payments import PAYMENT_METHODS, generate_payment_reference, normalize_iraqi_phone, validate_payment_method
from services.audit import write_audit_log
from services.notifications import create_notification
from services.payments import require_booking_payment_match, wallet_summary
from utils import PaginatedResponse, PaginationParams, paginate_query


router = APIRouter(prefix="/payments", tags=["المدفوعات والمحفظة"])


def verify_webhook_signature(payload: schemas.PaymentWebhookPayload) -> None:
    secret = get_settings().payment_webhook_secret
    if not secret:
        return
    if not payload.signature:
        raise HTTPException(status_code=401, detail="توقيع Webhook مفقود")
    message = f"{payload.provider}:{payload.reference}:{payload.status}:{payload.amount or ''}"
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload.signature):
        raise HTTPException(status_code=401, detail="توقيع Webhook غير صحيح")


@router.get("/wallet")
def get_my_wallet(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return wallet_summary(db, current_user.id)


@router.get("/methods")
def get_payment_methods():
    return {
        "methods": [
            {"code": code, **details}
            for code, details in PAYMENT_METHODS.items()
        ]
    }


@router.get("/transactions", response_model=PaginatedResponse)
def get_my_transactions(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.WalletTransaction).filter(
        models.WalletTransaction.user_id == current_user.id,
        models.WalletTransaction.is_deleted == False,
    ).order_by(models.WalletTransaction.created_at.desc())
    return paginate_query(query, pagination)


@router.post("/manual")
def submit_manual_payment(
    payload: schemas.ManualPaymentCreate,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db),
):
    booking = db.query(models.TutorBooking).filter(
        models.TutorBooking.id == payload.booking_id,
        models.TutorBooking.student_id == current_student.id,
        models.TutorBooking.is_deleted == False,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="الحجز غير موجود")

    require_booking_payment_match(booking, payload.amount)

    existing = db.query(models.WalletTransaction).filter(
        models.WalletTransaction.booking_id == booking.id,
        models.WalletTransaction.user_id == current_student.id,
        models.WalletTransaction.type == "manual_payment",
        models.WalletTransaction.status == "pending",
        models.WalletTransaction.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="يوجد طلب دفع قيد المراجعة لهذا الحجز")

    transaction = models.WalletTransaction(
        user_id=current_student.id,
        booking_id=booking.id,
        amount=payload.amount,
        type="manual_payment",
        status="pending",
        reference=payload.reference.strip(),
    )
    booking.payment_status = "review"
    db.add(transaction)
    write_audit_log(
        db,
        action="submit_manual_payment",
        actor_id=current_student.id,
        target_type="tutor_booking",
        target_id=booking.id,
        details=f"reference={transaction.reference}",
    )
    db.commit()
    return {"message": "تم إرسال بيانات الدفع للمراجعة", "transaction_id": transaction.id}


@router.post("/iraq/phone")
def submit_iraqi_phone_payment(
    payload: schemas.IraqiPhonePaymentCreate,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db),
):
    method = validate_payment_method(payload.payment_method)
    phone = normalize_iraqi_phone(payload.payer_phone)
    booking = db.query(models.TutorBooking).filter(
        models.TutorBooking.id == payload.booking_id,
        models.TutorBooking.student_id == current_student.id,
        models.TutorBooking.is_deleted == False,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="الحجز غير موجود")

    require_booking_payment_match(booking, payload.amount)

    reference = payload.reference.strip() if payload.reference else generate_payment_reference(payload.payment_method)
    existing = db.query(models.WalletTransaction).filter(
        models.WalletTransaction.reference == reference,
        models.WalletTransaction.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="مرجع الدفع مستخدم سابقاً")

    transaction = models.WalletTransaction(
        user_id=current_student.id,
        booking_id=booking.id,
        amount=payload.amount,
        type="phone_payment",
        status="pending",
        reference=reference,
        payment_method=payload.payment_method,
        payer_phone=phone,
        provider_payload=f"method_kind={method['kind']}",
    )
    booking.payment_status = "review"
    db.add(transaction)
    write_audit_log(
        db,
        action="submit_iraqi_phone_payment",
        actor_id=current_student.id,
        target_type="tutor_booking",
        target_id=booking.id,
        details=f"method={payload.payment_method};reference={reference}",
    )
    db.commit()
    return {
        "message": "تم تسجيل عملية الدفع وهي بانتظار التأكيد",
        "transaction_id": transaction.id,
        "reference": reference,
        "method": method,
    }


@router.get("/admin/transactions", response_model=PaginatedResponse)
def get_all_transactions(
    status: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    query = db.query(models.WalletTransaction).filter(models.WalletTransaction.is_deleted == False)
    if status:
        query = query.filter(models.WalletTransaction.status == status)
    return paginate_query(query.order_by(models.WalletTransaction.created_at.desc()), pagination)


@router.post("/admin/transactions/{transaction_id}/decision")
def decide_manual_payment(
    transaction_id: int,
    payload: schemas.PaymentDecision,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    transaction = db.query(models.WalletTransaction).filter(
        models.WalletTransaction.id == transaction_id,
        models.WalletTransaction.type.in_(["manual_payment", "phone_payment", "gateway_payment"]),
        models.WalletTransaction.is_deleted == False,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="عملية الدفع غير موجودة")
    if transaction.status != "pending":
        raise HTTPException(status_code=400, detail="تمت مراجعة هذه العملية سابقاً")

    booking = db.query(models.TutorBooking).filter(
        models.TutorBooking.id == transaction.booking_id,
        models.TutorBooking.is_deleted == False,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="الحجز المرتبط غير موجود")

    if payload.status == "approved":
        transaction.status = "approved"
        booking.payment_status = "paid"
        db.query(models.WalletTransaction).filter(
            models.WalletTransaction.booking_id == booking.id,
            models.WalletTransaction.type.in_(["payment", "earning"]),
            models.WalletTransaction.status == "pending",
        ).update({"status": "approved"}, synchronize_session=False)
        create_notification(db, booking.student_id, "تم تأكيد الدفع", "تمت مراجعة دفعتك وتأكيد حجز الحصة الخصوصية.", "payment_approved", send_email=True)
        create_notification(db, booking.tutor_id, "تم تأكيد حجز مدفوع", "تم تأكيد دفع الطالب لحصة خصوصية لديك.", "payment_approved", send_email=True)
    else:
        transaction.status = "rejected"
        booking.payment_status = "unpaid"
        create_notification(
            db,
            booking.student_id,
            "تم رفض الدفع",
            payload.note or "لم يتم قبول بيانات الدفع المرسلة، يرجى مراجعة الإدارة.",
            "payment_rejected",
            send_email=True,
        )

    write_audit_log(
        db,
        action=f"manual_payment_{payload.status}",
        actor_id=current_owner.id,
        target_type="wallet_transaction",
        target_id=transaction.id,
        details=payload.note,
    )
    db.commit()
    return {"message": "تم تحديث حالة الدفع", "status": transaction.status}


@router.post("/webhook")
def payment_webhook(
    payload: schemas.PaymentWebhookPayload,
    db: Session = Depends(get_db),
):
    verify_webhook_signature(payload)
    transaction = db.query(models.WalletTransaction).filter(
        models.WalletTransaction.reference == payload.reference,
            models.WalletTransaction.type.in_(["manual_payment", "phone_payment", "gateway_payment"]),
        models.WalletTransaction.is_deleted == False,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="مرجع الدفع غير معروف")

    booking = db.query(models.TutorBooking).filter(
        models.TutorBooking.id == transaction.booking_id,
        models.TutorBooking.is_deleted == False,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="الحجز المرتبط غير موجود")
    if payload.amount is not None and round(payload.amount, 2) != round(float(transaction.amount or 0), 2):
        raise HTTPException(status_code=400, detail="مبلغ Webhook لا يطابق العملية")

    if payload.status == "approved":
        transaction.status = "approved"
        booking.payment_status = "paid"
        db.query(models.WalletTransaction).filter(
            models.WalletTransaction.booking_id == booking.id,
            models.WalletTransaction.type.in_(["payment", "earning"]),
            models.WalletTransaction.status == "pending",
        ).update({"status": "approved"}, synchronize_session=False)
        create_notification(db, booking.student_id, "تم تأكيد الدفع", "وصل تأكيد الدفع من مزود الدفع.", "payment_approved", send_email=True)
        create_notification(db, booking.tutor_id, "تم تأكيد حجز مدفوع", "وصل تأكيد دفع لحصة خصوصية لديك.", "payment_approved", send_email=True)
    else:
        transaction.status = "rejected" if payload.status == "rejected" else "failed"
        booking.payment_status = "unpaid"
        create_notification(db, booking.student_id, "تعذر تأكيد الدفع", "لم يتم اعتماد عملية الدفع من مزود الدفع.", "payment_rejected", send_email=True)

    write_audit_log(
        db,
        action=f"payment_webhook_{payload.status}",
        target_type="wallet_transaction",
        target_id=transaction.id,
        details=f"provider={payload.provider};reference={payload.reference}",
    )
    db.commit()
    return {"message": "تمت معالجة Webhook", "status": transaction.status}
