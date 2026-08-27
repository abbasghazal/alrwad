from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
import models
import schemas
import auth
from permissions.dependencies import require
from services.audit import write_audit_log
from utils import PaginatedResponse, PaginationParams, ensure_aware_utc, now_utc, paginate_query

router = APIRouter(prefix="/lectures", tags=["المحاضرات"])


def teacher_can_manage_subject(db: Session, teacher: models.User, subject_id: int) -> bool:
    if teacher.role != "teacher":
        return False
    if teacher.subject_id == subject_id:
        return True
    return db.query(models.TeacherSubject).filter(
        models.TeacherSubject.teacher_id == teacher.id,
        models.TeacherSubject.subject_id == subject_id,
        models.TeacherSubject.is_deleted == False,
    ).first() is not None


def resolve_teacher_subject(db: Session, teacher: models.User, requested_subject_id: Optional[int] = None) -> int:
    subject_id = requested_subject_id or teacher.subject_id
    if not subject_id:
        link = db.query(models.TeacherSubject).filter(
            models.TeacherSubject.teacher_id == teacher.id,
            models.TeacherSubject.is_deleted == False,
        ).first()
        subject_id = link.subject_id if link else None
    if not subject_id or not teacher_can_manage_subject(db, teacher, subject_id):
        raise HTTPException(status_code=400, detail="المدرس الحالي غير مرتبط بهذه المادة")
    return subject_id


def ensure_no_schedule_conflict(db: Session, subject_id: int, start_time, end_time, lecture_id: Optional[int] = None) -> None:
    query = db.query(models.Lecture).filter(
        models.Lecture.subject_id == subject_id,
        models.Lecture.is_deleted == False,
        models.Lecture.lecture_status != "cancelled",
        models.Lecture.start_time < end_time,
        models.Lecture.end_time > start_time,
    )
    if lecture_id:
        query = query.filter(models.Lecture.id != lecture_id)
    if query.first():
        raise HTTPException(status_code=400, detail="يوجد تعارض في موعد المحاضرة مع محاضرة أخرى")


@router.get("/today", response_model=PaginatedResponse)
def get_today_lectures(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    query = db.query(models.Lecture).filter(
        models.Lecture.start_time >= start,
        models.Lecture.start_time <= end,
        models.Lecture.is_deleted == False,
    )
    return paginate_query(query.order_by(models.Lecture.start_time.asc()), pagination)


@router.get("/upcoming", response_model=PaginatedResponse)
def get_upcoming_lectures(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Lecture).filter(
        models.Lecture.start_time >= now_utc(),
        models.Lecture.is_deleted == False,
        models.Lecture.lecture_status == "scheduled",
    )
    return paginate_query(query.order_by(models.Lecture.start_time.asc()), pagination)


@router.get("/live", response_model=PaginatedResponse)
def get_live_lectures(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Lecture).filter(
        models.Lecture.start_time <= now_utc(),
        models.Lecture.end_time >= now_utc(),
        models.Lecture.is_deleted == False,
    )
    return paginate_query(query.order_by(models.Lecture.start_time.asc()), pagination)

@router.get("/subject/{subject_id}", response_model=PaginatedResponse)
def get_lectures_by_subject(
    subject_id: int,
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """جلب المحاضرات الخاصة بمادة معينة"""
    # التحقق من أن الطالب مسجل في المادة، أو المالك، أو المعلم الذي يدرسها
    if current_user.role == "student":
        enrolled = db.query(models.Enrollment).filter(
            models.Enrollment.student_id == current_user.id,
            models.Enrollment.subject_id == subject_id,
            models.Enrollment.is_deleted == False,
            models.Enrollment.status == "active"
        ).first()
        if not enrolled:
            raise HTTPException(status_code=403, detail="يجب أن تسجل في المادة أولاً للوصول لمحاضراتها")
    elif current_user.role == "teacher":
        if not teacher_can_manage_subject(db, current_user, subject_id):
            raise HTTPException(status_code=403, detail="لا تملك صلاحية الوصول لمحاضرات هذه المادة")
            
    query = db.query(models.Lecture).filter(
        models.Lecture.subject_id == subject_id,
        models.Lecture.is_deleted == False
    ).order_by(models.Lecture.start_time.asc())
    return paginate_query(query, pagination)


@router.post("", response_model=schemas.LectureResponse)
def create_lecture(
    lecture_in: schemas.LectureCreate,
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """إضافة محاضرة جديدة (المدرس فقط - للمادة التي يدرسها تلقائياً)"""
    subject_id = resolve_teacher_subject(db, current_teacher, lecture_in.subject_id)
        
    if lecture_in.start_time >= lecture_in.end_time:
        raise HTTPException(status_code=400, detail="وقت بدء المحاضرة يجب أن يكون قبل وقت انتهائها")

    ensure_no_schedule_conflict(db, subject_id, lecture_in.start_time, lecture_in.end_time)
    new_lecture = models.Lecture(
        subject_id=subject_id,
        title=lecture_in.title,
        description=lecture_in.description,
        start_time=lecture_in.start_time,
        end_time=lecture_in.end_time,
        meeting_url=lecture_in.meeting_url,
        meeting_platform=lecture_in.meeting_platform,
        recording_url=lecture_in.recording_url,
        attachments=lecture_in.attachments,
        lecture_status=lecture_in.lecture_status or "scheduled",
    )
    
    db.add(new_lecture)
    
    # إرسال إشعارات للطلاب المسجلين في المادة
    students = db.query(models.Enrollment).filter(
        models.Enrollment.subject_id == subject_id,
        models.Enrollment.is_deleted == False,
        models.Enrollment.status == "active",
    ).all()
    
    for s in students:
        notif = models.Notification(
            user_id=s.student_id,
            title="محاضرة جديدة مضافة",
            message=f"قام الأستاذ بإضافة محاضرة جديدة بعنوان '{lecture_in.title}' تبدأ في {lecture_in.start_time.strftime('%Y/%m/%d %H:%M')}",
            type="lecture_start"
        )
        db.add(notif)
        
    db.commit()
    db.refresh(new_lecture)
    return new_lecture


@router.put("/{lecture_id}", response_model=schemas.LectureResponse)
def update_lecture(
    lecture_id: int,
    lecture_in: schemas.LectureCreate,
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """تعديل محاضرة (قبل بدء المحاضرة فقط)"""
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id, models.Lecture.is_deleted == False).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="المحاضرة غير موجودة")
        
    if not teacher_can_manage_subject(db, current_teacher, lecture.subject_id):
        raise HTTPException(status_code=403, detail="لا يمكنك تعديل محاضرات لست معلماً لها")
        
    # التحقق من أن موعد المحاضرة لم يبدأ بعد
    if ensure_aware_utc(lecture.start_time) < now_utc():
        raise HTTPException(status_code=400, detail="لا يمكن تعديل المحاضرة بعد بدء موعدها")
        
    if lecture_in.start_time >= lecture_in.end_time:
        raise HTTPException(status_code=400, detail="وقت بدء المحاضرة يجب أن يكون قبل وقت انتهائها")

    ensure_no_schedule_conflict(db, lecture.subject_id, lecture_in.start_time, lecture_in.end_time, lecture_id=lecture.id)
    lecture.title = lecture_in.title
    lecture.description = lecture_in.description
    lecture.start_time = lecture_in.start_time
    lecture.end_time = lecture_in.end_time
    lecture.meeting_url = lecture_in.meeting_url
    lecture.meeting_platform = lecture_in.meeting_platform
    lecture.recording_url = lecture_in.recording_url
    lecture.attachments = lecture_in.attachments
    lecture.lecture_status = lecture_in.lecture_status or lecture.lecture_status
    write_audit_log(db, action="update_lecture", actor_id=current_teacher.id, target_type="lecture", target_id=lecture.id)
    
    db.commit()
    db.refresh(lecture)
    return lecture


@router.delete("/{lecture_id}")
def delete_lecture(
    lecture_id: int,
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """حذف محاضرة (قبل بدء المحاضرة فقط)"""
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id, models.Lecture.is_deleted == False).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="المحاضرة غير موجودة")
        
    if not teacher_can_manage_subject(db, current_teacher, lecture.subject_id):
        raise HTTPException(status_code=403, detail="لا يمكنك حذف محاضرات لست معلماً لها")
        
    # التحقق من أن موعد المحاضرة لم يبدأ بعد
    if ensure_aware_utc(lecture.start_time) < now_utc():
        raise HTTPException(status_code=400, detail="لا يمكن حذف المحاضرة بعد بدء موعدها")
        
    lecture.is_deleted = True
    lecture.deleted_at = now_utc()
    lecture.deleted_by = current_teacher.id
    write_audit_log(db, action="delete_lecture", actor_id=current_teacher.id, target_type="lecture", target_id=lecture.id)
    db.commit()
    return {"message": "تم حذف المحاضرة بنجاح"}


@router.post("/{lecture_id}/attendance")
def upsert_attendance(
    lecture_id: int,
    payload: schemas.AttendanceUpdate,
    current_teacher: models.User = Depends(require("can_grade_students")),
    db: Session = Depends(get_db),
):
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id, models.Lecture.is_deleted == False).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="المحاضرة غير موجودة")
    if not teacher_can_manage_subject(db, current_teacher, lecture.subject_id):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية تسجيل حضور هذه المحاضرة")

    attendance = db.query(models.LectureAttendance).filter(
        models.LectureAttendance.lecture_id == lecture_id,
        models.LectureAttendance.student_id == payload.student_id,
        models.LectureAttendance.is_deleted == False,
    ).first()
    if not attendance:
        attendance = models.LectureAttendance(lecture_id=lecture_id, student_id=payload.student_id)
        db.add(attendance)
    attendance.status = payload.status
    attendance.joined_at = payload.joined_at
    attendance.left_at = payload.left_at
    write_audit_log(db, action="mark_attendance", actor_id=current_teacher.id, target_type="lecture", target_id=lecture_id)
    db.commit()
    return {"message": "تم تحديث الحضور بنجاح"}


@router.get("/{lecture_id}/attendance")
def get_attendance(
    lecture_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id, models.Lecture.is_deleted == False).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="المحاضرة غير موجودة")
    if current_user.role == "teacher" and not teacher_can_manage_subject(db, current_user, lecture.subject_id):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية عرض حضور هذه المحاضرة")
    if current_user.role == "student":
        query = db.query(models.LectureAttendance).filter(
            models.LectureAttendance.lecture_id == lecture_id,
            models.LectureAttendance.student_id == current_user.id,
            models.LectureAttendance.is_deleted == False,
        )
    else:
        query = db.query(models.LectureAttendance).filter(
            models.LectureAttendance.lecture_id == lecture_id,
            models.LectureAttendance.is_deleted == False,
        )
    return query.all()
