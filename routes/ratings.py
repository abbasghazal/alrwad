from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from database import get_db
import models
import schemas
import auth
from permissions.dependencies import require
from services.audit import write_audit_log
from utils import PaginatedResponse, PaginationParams, now_utc, paginate_query

router = APIRouter(prefix="/ratings", tags=["تقييم المدرسين"])


def teacher_subject_ids(db: Session, teacher_id: int, fallback_subject_id: Optional[int]) -> List[int]:
    ids = [
        row.subject_id
        for row in db.query(models.TeacherSubject).filter(
            models.TeacherSubject.teacher_id == teacher_id,
            models.TeacherSubject.is_deleted == False,
        ).all()
    ]
    if fallback_subject_id and fallback_subject_id not in ids:
        ids.append(fallback_subject_id)
    return ids

@router.post("", response_model=schemas.RatingResponse)
def create_rating(
    payload: schemas.RatingCreate,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db)
):
    """إضافة تقييم لمعلم من قبل الطالب"""
    # التحقق من أن المدرس موجود بالفعل
    teacher = db.query(models.User).filter(
        models.User.id == payload.teacher_id,
        models.User.role == "teacher",
        models.User.is_deleted == False
    ).first()
    
    if not teacher:
        raise HTTPException(status_code=404, detail="المعلم غير موجود")
        
    # التحقق من أن الطالب مسجل في مادة هذا المدرس
    subject_ids = teacher_subject_ids(db, teacher.id, teacher.subject_id)
    enrolled = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_student.id,
        models.Enrollment.subject_id.in_(subject_ids),
        models.Enrollment.is_deleted == False,
        models.Enrollment.status == "active",
    ).first()
    
    if not enrolled:
        raise HTTPException(status_code=400, detail="لا يمكنك تقييم معلم لم تدرس عنده")
        
    # التحقق من أن الطالب لم يقيم المدرس مسبقاً لهذه المادة
    existing_rating = db.query(models.Rating).filter(
        models.Rating.student_id == current_student.id,
        models.Rating.teacher_id == payload.teacher_id,
        models.Rating.subject_id == enrolled.subject_id,
        models.Rating.is_deleted == False,
    ).first()
    
    if existing_rating:
        raise HTTPException(status_code=400, detail="لقد قمت بتقييم هذا المدرس لهذه المادة مسبقاً")
        
    # إضافة التقييم
    new_rating = models.Rating(
        teacher_id=payload.teacher_id,
        student_id=current_student.id,
        subject_id=enrolled.subject_id,
        stars=payload.stars,
        comment=payload.comment
    )
    db.add(new_rating)
    
    # إرسال إشعار للمدرس بالتقييم الجديد
    notif = models.Notification(
        user_id=payload.teacher_id,
        title="تقييم جديد",
        message=f"قام أحد الطلاب بتقييمك بـ {payload.stars} نجوم",
        type="teacher_rated"
    )
    db.add(notif)
    write_audit_log(db, action="create_rating", actor_id=current_student.id, target_type="rating")
    db.commit()
    db.refresh(new_rating)
    return new_rating


@router.get("/teacher/{teacher_id}", response_model=PaginatedResponse)
def get_teacher_ratings(
    teacher_id: int,
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """عرض تقييمات معلم معين (المعلم نفسه أو المالك فقط)"""
    if current_user.role == "teacher" and current_user.id != teacher_id:
         raise HTTPException(status_code=403, detail="لا تملك صلاحيات استعراض تقييمات معلم آخر")
         
    query = db.query(models.Rating).filter(
        models.Rating.teacher_id == teacher_id,
        models.Rating.is_deleted == False
    ).order_by(models.Rating.created_at.desc())
    return paginate_query(query, pagination)


@router.get("/teacher/{teacher_id}/stats")
def get_teacher_rating_stats(teacher_id: int, db: Session = Depends(get_db)):
    """احتساب متوسط التقييم لمعلم"""
    stats = db.query(
        func.avg(models.Rating.stars).label("average"),
        func.count(models.Rating.id).label("count")
    ).filter(models.Rating.teacher_id == teacher_id, models.Rating.is_deleted == False).first()
    
    average = round(stats.average, 2) if stats.average else 0.0
    count = stats.count if stats.count else 0
    
    return {"average_rating": average, "total_ratings": count}


@router.get("/teacher/{teacher_id}/rating-summary")
def get_teacher_rating_summary(teacher_id: int, db: Session = Depends(get_db)):
    stats = get_teacher_rating_stats(teacher_id=teacher_id, db=db)
    distribution = dict(
        db.query(models.Rating.stars, func.count(models.Rating.id))
        .filter(models.Rating.teacher_id == teacher_id, models.Rating.is_deleted == False)
        .group_by(models.Rating.stars)
        .all()
    )
    stats["distribution"] = {str(stars): distribution.get(stars, 0) for stars in range(1, 6)}
    return stats


@router.put("/{rating_id}", response_model=schemas.RatingResponse)
def update_rating(
    rating_id: int,
    payload: schemas.RatingCreate,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db),
):
    rating = db.query(models.Rating).filter(
        models.Rating.id == rating_id,
        models.Rating.student_id == current_student.id,
        models.Rating.is_deleted == False,
    ).first()
    if not rating:
        raise HTTPException(status_code=404, detail="التقييم غير موجود")
    rating.stars = payload.stars
    rating.comment = payload.comment
    write_audit_log(db, action="update_rating", actor_id=current_student.id, target_type="rating", target_id=rating.id)
    db.commit()
    db.refresh(rating)
    return rating


@router.delete("/{rating_id}")
def delete_rating(
    rating_id: int,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db)
):
    """حذف تقييم مسيء أو غير لائق (المالك فقط)"""
    rating = db.query(models.Rating).filter(models.Rating.id == rating_id, models.Rating.is_deleted == False).first()
    if not rating:
        raise HTTPException(status_code=404, detail="التقييم غير موجود")
        
    rating.is_deleted = True
    rating.deleted_at = now_utc()
    rating.deleted_by = current_owner.id
    write_audit_log(db, action="delete_rating", actor_id=current_owner.id, target_type="rating", target_id=rating.id)
    db.commit()
    return {"message": "تم حذف التقييم بنجاح"}
