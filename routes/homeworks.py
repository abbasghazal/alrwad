import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from database import get_db
import models
import schemas
import auth
from services.audit import write_audit_log
from services.storage import StorageService
from utils import PaginatedResponse, PaginationParams, ensure_aware_utc, now_utc, paginate_query, safe_delete_static_file, upload_subdir_path, upload_url

router = APIRouter(prefix="/homeworks", tags=["الواجبات والتقييمات الأكاديمية"])

UPLOAD_DIR = upload_subdir_path("homeworks")
MAX_HOMEWORK_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_HOMEWORK_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".zip", ".rar", ".txt"}


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


def validate_upload(file: UploadFile) -> str:
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_HOMEWORK_EXTS:
        raise HTTPException(status_code=400, detail="نوع الملف غير مسموح به")
    head = file.file.read(2048)
    file.file.seek(0)
    lowered = head.lower()
    if head.startswith(b"MZ") or b"<?php" in lowered or b"<script" in lowered:
        raise HTTPException(status_code=400, detail="محتوى الملف غير آمن")
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_HOMEWORK_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="حجم الملف يتجاوز الحد المسموح 10MB")
    return file_ext

@router.get("/subject/{subject_id}", response_model=PaginatedResponse)
def get_homeworks_by_subject(
    subject_id: int,
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """جلب قائمة واجبات المادة"""
    if current_user.role == "student":
        enrolled = db.query(models.Enrollment).filter(
            models.Enrollment.student_id == current_user.id,
            models.Enrollment.subject_id == subject_id,
            models.Enrollment.is_deleted == False,
            models.Enrollment.status == "active"
        ).first()
        if not enrolled:
            raise HTTPException(status_code=403, detail="يجب التسجيل في المادة لمشاهدة واجباتها")
    elif current_user.role == "teacher":
        if not teacher_can_manage_subject(db, current_user, subject_id):
            raise HTTPException(status_code=403, detail="غير مصرح بمشاهدة واجبات مادة أخرى")
            
    query = db.query(models.Homework).filter(
        models.Homework.subject_id == subject_id,
        models.Homework.is_deleted == False
    ).order_by(models.Homework.created_at.desc())
    return paginate_query(query, pagination)


@router.post("")
def create_homework(
    title: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(...),
    subject_id: Optional[int] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """إضافة واجب جديد من قبل المدرس"""
    resolved_subject_id = resolve_teacher_subject(db, current_teacher, subject_id)
        
    try:
        deadline_dt = ensure_aware_utc(datetime.fromisoformat(deadline.replace("Z", "+00:00")))
    except ValueError:
        raise HTTPException(status_code=400, detail="صيغة التاريخ غير صحيحة، يرجى إرسال ISO 8601")
        
    file_url = None
    if file:
        file_ext = validate_upload(file)
        file_url = StorageService().save(file.file, "homeworks", file_ext).url

    new_homework = models.Homework(
        subject_id=resolved_subject_id,
        title=title,
        description=description,
        deadline=deadline_dt,
        file_url=file_url
    )
    db.add(new_homework)
    
    # إرسال إشعار للطلاب
    students = db.query(models.Enrollment).filter(
        models.Enrollment.subject_id == resolved_subject_id,
        models.Enrollment.is_deleted == False,
        models.Enrollment.status == "active",
    ).all()
    
    for s in students:
        notif = models.Notification(
            user_id=s.student_id,
            title="واجب جديد مطلوب",
            message=f"تمت إضافة واجب جديد بعنوان '{title}'، الموعد النهائي: {deadline_dt.strftime('%Y/%m/%d %H:%M')}",
            type="homework_deadline"
        )
        db.add(notif)
        
    write_audit_log(db, action="create_homework", actor_id=current_teacher.id, target_type="homework")
    db.commit()
    db.refresh(new_homework)
    return {"message": "تمت إضافة الواجب بنجاح", "homework_id": new_homework.id}


@router.post("/{homework_id}/submit")
def submit_homework(
    homework_id: int,
    file: UploadFile = File(...),
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db)
):
    """تسليم واجب من الطالب"""
    homework = db.query(models.Homework).filter(models.Homework.id == homework_id, models.Homework.is_deleted == False).first()
    if not homework:
        raise HTTPException(status_code=404, detail="الواجب غير موجود")
        
    # التحقق من أن الطالب مسجل في مادة الواجب
    enrolled = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_student.id,
        models.Enrollment.subject_id == homework.subject_id,
        models.Enrollment.is_deleted == False,
        models.Enrollment.status == "active"
    ).first()
    if not enrolled:
        raise HTTPException(status_code=403, detail="يجب أن تكون مسجلاً في هذه المادة لتسليم الواجب")
        
    # حفظ الملف
    file_ext = validate_upload(file)
    file_url = StorageService().save(file.file, "homeworks", file_ext).url
    
    # التحقق من أن حالة التسليم متأخرة أو لا
    status_str = "submitted"
    if now_utc() > ensure_aware_utc(homework.deadline):
        status_str = "late"

    # التحقق من وجود تسليم سابق
    existing_sub = db.query(models.Submission).filter(
        models.Submission.homework_id == homework_id,
        models.Submission.student_id == current_student.id,
        models.Submission.is_deleted == False,
    ).first()
    
    if existing_sub:
        # حذف الملف القديم محلياً لتوفير المساحة
        safe_delete_static_file(existing_sub.file_url, "uploads/homeworks/")
                
        # تحديث التسليم الحالي
        existing_sub.file_url = file_url
        existing_sub.submitted_at = now_utc()
        existing_sub.status = status_str
        db.commit()
    else:
        # إنشاء تسليم جديد
        new_sub = models.Submission(
            homework_id=homework_id,
            student_id=current_student.id,
            file_url=file_url,
            status=status_str
        )
        db.add(new_sub)
        
    # إرسال إشعار للمدرس
    teacher = db.query(models.User).filter(
        models.User.role == "teacher",
        models.User.subject_id == homework.subject_id
    ).first()
    
    if teacher:
        notif = models.Notification(
            user_id=teacher.id,
            title="تسليم واجب جديد",
            message=f"قام الطالب {current_student.first_name} {current_student.last_name} بتسليم واجب '{homework.title}'",
            type="homework_submitted"
        )
        db.add(notif)
        
    db.commit()
    return {"message": "تم تسليم الواجب بنجاح", "file_url": file_url}


@router.delete("/{homework_id}")
def delete_homework(
    homework_id: int,
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """حذف واجب وملفاته المرتبطة من قبل مدرس المادة"""
    homework = db.query(models.Homework).filter(models.Homework.id == homework_id, models.Homework.is_deleted == False).first()
    if not homework:
        raise HTTPException(status_code=404, detail="الواجب غير موجود")

    if not teacher_can_manage_subject(db, current_teacher, homework.subject_id):
        raise HTTPException(status_code=403, detail="لا يمكنك حذف واجبات لست معلماً لها")

    homework.is_deleted = True
    homework.deleted_at = now_utc()
    homework.deleted_by = current_teacher.id
    write_audit_log(db, action="delete_homework", actor_id=current_teacher.id, target_type="homework", target_id=homework.id)
    db.commit()
    return {"message": "تم حذف الواجب بنجاح"}


@router.get("/my/submissions", response_model=PaginatedResponse)
def get_my_submissions(
    pagination: PaginationParams = Depends(),
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db)
):
    """جلب تسليمات الطالب الحالي لمراجعتها"""
    query = db.query(models.Submission).filter(
        models.Submission.student_id == current_student.id,
        models.Submission.is_deleted == False,
    ).order_by(models.Submission.submitted_at.desc())
    return paginate_query(query, pagination)


@router.get("/{homework_id}/submissions", response_model=PaginatedResponse)
def get_submissions(
    homework_id: int,
    pagination: PaginationParams = Depends(),
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """عرض تسليمات الطلاب لواجب معين (المدرس فقط)"""
    homework = db.query(models.Homework).filter(models.Homework.id == homework_id, models.Homework.is_deleted == False).first()
    if not homework:
        raise HTTPException(status_code=404, detail="الواجب غير موجود")
        
    if not teacher_can_manage_subject(db, current_teacher, homework.subject_id):
        raise HTTPException(status_code=403, detail="غير مصرح بمشاهدة تسليمات هذا الواجب")
        
    query = db.query(models.Submission).filter(
        models.Submission.homework_id == homework_id,
        models.Submission.is_deleted == False,
    ).order_by(models.Submission.submitted_at.desc())
    return paginate_query(query, pagination)


@router.post("/submissions/{submission_id}/grade")
def grade_submission(
    submission_id: int,
    payload: schemas.SubmissionGrade,
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """تصحيح الواجب من قبل المدرس"""
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id, models.Submission.is_deleted == False).first()
    if not submission:
        raise HTTPException(status_code=404, detail="التسليم غير موجود")
        
    homework = submission.homework
    if not teacher_can_manage_subject(db, current_teacher, homework.subject_id):
        raise HTTPException(status_code=403, detail="لا تملك صلاحيات تصحيح هذا الواجب")
        
    submission.grade = payload.grade
    submission.teacher_notes = payload.teacher_notes
    submission.status = "completed"
    write_audit_log(db, action="grade_submission", actor_id=current_teacher.id, target_type="submission", target_id=submission.id)
    
    # إشعار الطالب بالدرجة
    notif = models.Notification(
        user_id=submission.student_id,
        title="تم تصحيح واجبك",
        message=f"قام الأستاذ بتصحيح واجبك '{homework.title}' وحصلت على درجة {payload.grade}",
        type="homework_graded"
    )
    db.add(notif)
    db.commit()
    return {"message": "تم رصد الدرجة والملاحظات بنجاح"}
