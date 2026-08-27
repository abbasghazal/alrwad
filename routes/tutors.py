from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

import auth
import models
import schemas
from database import get_db
from permissions.dependencies import require
from services.audit import write_audit_log
from utils import PaginatedResponse, PaginationParams, ensure_aware_utc, now_utc, paginate_query


router = APIRouter(prefix="/tutors", tags=["المدرسون الخصوصيون"])


@router.get("/search", response_model=PaginatedResponse)
def search_tutors(
    q: str = Query("", min_length=0),
    specialty: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
):
    query = db.query(models.User).filter(
        models.User.role == "tutor",
        models.User.is_deleted == False,
        models.User.is_blocked == False,
    )
    if q:
        search = f"%{q}%"
        query = query.filter(
            (models.User.first_name.ilike(search)) |
            (models.User.last_name.ilike(search)) |
            (models.User.username.ilike(search)) |
            (models.User.specialty.ilike(search))
        )
    if specialty:
        query = query.filter(models.User.specialty.ilike(f"%{specialty}%"))
    return paginate_query(query.order_by(models.User.created_at.desc()), pagination)


@router.get("/{tutor_id}/stats")
def tutor_stats(tutor_id: int, db: Session = Depends(get_db)):
    tutor = db.query(models.User).filter(
        models.User.id == tutor_id,
        models.User.role == "tutor",
        models.User.is_deleted == False,
    ).first()
    if not tutor:
        raise HTTPException(status_code=404, detail="المدرس الخصوصي غير موجود")
    rating = db.query(
        func.avg(models.TutorReview.stars).label("average"),
        func.count(models.TutorReview.id).label("count"),
    ).filter(models.TutorReview.tutor_id == tutor_id, models.TutorReview.is_deleted == False).first()
    completed = db.query(models.TutorBooking).filter(
        models.TutorBooking.tutor_id == tutor_id,
        models.TutorBooking.status == "completed",
        models.TutorBooking.is_deleted == False,
    ).count()
    upcoming = db.query(models.TutorBooking).filter(
        models.TutorBooking.tutor_id == tutor_id,
        models.TutorBooking.start_time >= now_utc(),
        models.TutorBooking.is_deleted == False,
    ).count()
    return {
        "average_rating": round(rating.average, 2) if rating.average else 0,
        "total_reviews": rating.count or 0,
        "completed_sessions": completed,
        "upcoming_sessions": upcoming,
        "hourly_rate": tutor.hourly_rate or 0,
    }


@router.post("/availability")
def create_availability(
    payload: schemas.TutorAvailabilityCreate,
    current_tutor: models.User = Depends(require("can_manage_tutors")),
    db: Session = Depends(get_db),
):
    if current_tutor.role != "tutor":
        raise HTTPException(status_code=403, detail="هذا الإجراء للمدرسين الخصوصيين فقط")
    start_time = ensure_aware_utc(payload.start_time)
    end_time = ensure_aware_utc(payload.end_time)
    if start_time >= end_time:
        raise HTTPException(status_code=400, detail="وقت البداية يجب أن يكون قبل النهاية")
    overlap = db.query(models.TutorAvailability).filter(
        models.TutorAvailability.tutor_id == current_tutor.id,
        models.TutorAvailability.is_deleted == False,
        models.TutorAvailability.start_time < end_time,
        models.TutorAvailability.end_time > start_time,
    ).first()
    if overlap:
        raise HTTPException(status_code=400, detail="يوجد تعارض مع موعد متاح سابق")
    row = models.TutorAvailability(tutor_id=current_tutor.id, start_time=start_time, end_time=end_time)
    db.add(row)
    write_audit_log(db, action="create_tutor_availability", actor_id=current_tutor.id, target_type="tutor")
    db.commit()
    return {"message": "تمت إضافة الموعد المتاح بنجاح", "id": row.id}


@router.get("/{tutor_id}/availability")
def get_availability(tutor_id: int, db: Session = Depends(get_db)):
    return db.query(models.TutorAvailability).filter(
        models.TutorAvailability.tutor_id == tutor_id,
        models.TutorAvailability.is_deleted == False,
        models.TutorAvailability.is_booked == False,
        models.TutorAvailability.end_time >= now_utc(),
    ).order_by(models.TutorAvailability.start_time.asc()).all()


@router.post("/book-session")
def book_session(
    payload: schemas.TutorBookingCreate,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db),
):
    tutor = db.query(models.User).filter(
        models.User.id == payload.tutor_id,
        models.User.role == "tutor",
        models.User.is_deleted == False,
        models.User.is_blocked == False,
    ).first()
    if not tutor:
        raise HTTPException(status_code=404, detail="المدرس الخصوصي غير موجود")

    availability = None
    if payload.availability_id:
        availability = db.query(models.TutorAvailability).filter(
            models.TutorAvailability.id == payload.availability_id,
            models.TutorAvailability.tutor_id == tutor.id,
            models.TutorAvailability.is_deleted == False,
            models.TutorAvailability.is_booked == False,
        ).first()
        if not availability:
            raise HTTPException(status_code=400, detail="الموعد غير متاح")
        start_time = availability.start_time
        end_time = availability.end_time
    else:
        if not payload.start_time or not payload.end_time:
            raise HTTPException(status_code=400, detail="يجب تحديد موعد الحصة")
        start_time = ensure_aware_utc(payload.start_time)
        end_time = ensure_aware_utc(payload.end_time)

    if start_time >= end_time:
        raise HTTPException(status_code=400, detail="وقت البداية يجب أن يكون قبل النهاية")
    conflict = db.query(models.TutorBooking).filter(
        models.TutorBooking.tutor_id == tutor.id,
        models.TutorBooking.is_deleted == False,
        models.TutorBooking.status.in_(["pending", "confirmed"]),
        models.TutorBooking.start_time < end_time,
        models.TutorBooking.end_time > start_time,
    ).first()
    if conflict:
        raise HTTPException(status_code=400, detail="الموعد محجوز بالفعل")

    duration = int((end_time - start_time).total_seconds() // 60)
    price = round((duration / 60) * (tutor.hourly_rate or 0), 2)
    booking = models.TutorBooking(
        tutor_id=tutor.id,
        student_id=current_student.id,
        availability_id=availability.id if availability else None,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration,
        meeting_url=f"https://meet.example.com/tutor-{tutor.id}-{current_student.id}",
        status="confirmed",
        price=price,
        payment_status="pending",
    )
    db.add(booking)
    if availability:
        availability.is_booked = True
    db.flush()
    db.add(models.WalletTransaction(user_id=current_student.id, booking_id=booking.id, amount=-price, type="payment", status="pending"))
    db.add(models.WalletTransaction(user_id=tutor.id, booking_id=booking.id, amount=price, type="earning", status="pending"))
    write_audit_log(db, action="book_tutor_session", actor_id=current_student.id, target_type="tutor_booking", target_id=booking.id)
    db.commit()
    return {"message": "تم حجز الحصة بنجاح", "booking_id": booking.id, "meeting_url": booking.meeting_url, "price": price}


@router.get("/bookings/my", response_model=PaginatedResponse)
def get_my_tutor_bookings(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.TutorBooking).filter(models.TutorBooking.is_deleted == False)
    if current_user.role == "student":
        query = query.filter(models.TutorBooking.student_id == current_user.id)
    elif current_user.role == "tutor":
        query = query.filter(models.TutorBooking.tutor_id == current_user.id)
    else:
        raise HTTPException(status_code=403, detail="هذه الصفحة للطلاب والمدرسين الخصوصيين فقط")
    return paginate_query(query.order_by(models.TutorBooking.start_time.desc()), pagination)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.query(models.TutorBooking).filter(
        models.TutorBooking.id == booking_id,
        models.TutorBooking.is_deleted == False,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="الحجز غير موجود")
    if current_user.id not in {booking.student_id, booking.tutor_id} and current_user.role != "owner":
        raise HTTPException(status_code=403, detail="لا تملك صلاحية إلغاء هذا الحجز")
    if booking.status in {"completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء هذا الحجز")
    if ensure_aware_utc(booking.start_time) <= now_utc() and current_user.role != "owner":
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء الحجز بعد بداية موعده")

    booking.status = "cancelled"
    if booking.availability:
        booking.availability.is_booked = False
    db.query(models.WalletTransaction).filter(
        models.WalletTransaction.booking_id == booking.id,
        models.WalletTransaction.status == "pending",
    ).update({"status": "cancelled"}, synchronize_session=False)
    db.add(models.Notification(
        user_id=booking.student_id if current_user.id == booking.tutor_id else booking.tutor_id,
        title="تم إلغاء حجز",
        message="تم إلغاء إحدى الحصص الخصوصية المرتبطة بحسابك.",
        type="booking_cancelled",
    ))
    write_audit_log(db, action="cancel_tutor_booking", actor_id=current_user.id, target_type="tutor_booking", target_id=booking.id)
    db.commit()
    return {"message": "تم إلغاء الحجز بنجاح"}


@router.post("/bookings/{booking_id}/complete")
def complete_booking(
    booking_id: int,
    current_tutor: models.User = Depends(require("can_manage_tutors")),
    db: Session = Depends(get_db),
):
    if current_tutor.role != "tutor":
        raise HTTPException(status_code=403, detail="هذا الإجراء للمدرس الخصوصي فقط")
    booking = db.query(models.TutorBooking).filter(
        models.TutorBooking.id == booking_id,
        models.TutorBooking.tutor_id == current_tutor.id,
        models.TutorBooking.is_deleted == False,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="الحجز غير موجود")
    if booking.status != "confirmed":
        raise HTTPException(status_code=400, detail="يمكن إكمال الحجز المؤكد فقط")
    if booking.payment_status != "paid":
        raise HTTPException(status_code=400, detail="لا يمكن إكمال الحصة قبل تأكيد الدفع")

    booking.status = "completed"
    db.query(models.WalletTransaction).filter(
        models.WalletTransaction.booking_id == booking.id,
        models.WalletTransaction.status == "approved",
    ).update({"status": "completed"}, synchronize_session=False)
    db.add(models.Notification(
        user_id=booking.student_id,
        title="اكتملت الحصة الخصوصية",
        message="تم تعليم الحصة الخصوصية كمكتملة ويمكنك الآن إضافة تقييمك.",
        type="booking_completed",
    ))
    write_audit_log(db, action="complete_tutor_booking", actor_id=current_tutor.id, target_type="tutor_booking", target_id=booking.id)
    db.commit()
    return {"message": "تم تعليم الحصة كمكتملة"}


@router.post("/reviews")
def create_review(
    payload: schemas.TutorReviewCreate,
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
    if booking.status != "completed":
        raise HTTPException(status_code=400, detail="يمكن تقييم الحصة بعد اكتمالها فقط")
    existing = db.query(models.TutorReview).filter(
        models.TutorReview.booking_id == booking.id,
        models.TutorReview.student_id == current_student.id,
        models.TutorReview.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="تم تقييم هذه الحصة سابقاً")
    review = models.TutorReview(
        booking_id=booking.id,
        tutor_id=booking.tutor_id,
        student_id=current_student.id,
        stars=payload.stars,
        comment=payload.comment,
    )
    db.add(review)
    write_audit_log(db, action="create_tutor_review", actor_id=current_student.id, target_type="tutor_booking", target_id=booking.id)
    db.commit()
    return {"message": "تم إضافة التقييم بنجاح"}
