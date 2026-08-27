from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
import models
import schemas
import auth
from permissions.dependencies import require
from services.audit import write_audit_log
from utils import PaginatedResponse, PaginationParams, now_utc, paginate_query

router = APIRouter(prefix="/subjects", tags=["المواد الدراسية"])

@router.get("", response_model=PaginatedResponse)
def get_subjects(
    grade_level: Optional[str] = Query(None, description="فلترة حسب الصف الدراسي"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db)
):
    query = db.query(models.Subject).filter(models.Subject.is_deleted == False)
    if grade_level:
        query = query.filter(models.Subject.grade_level == grade_level)
    return paginate_query(query.order_by(models.Subject.created_at.desc()), pagination)


@router.get("/search", response_model=PaginatedResponse)
def search_subjects(
    q: Optional[str] = Query(None),
    grade_level: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
):
    query = db.query(models.Subject).filter(models.Subject.is_deleted == False)
    if q:
        search_filter = f"%{q}%"
        query = query.filter(
            (models.Subject.name.ilike(search_filter)) |
            (models.Subject.description.ilike(search_filter))
        )
    if grade_level:
        query = query.filter(models.Subject.grade_level == grade_level)
    return paginate_query(query.order_by(models.Subject.created_at.desc()), pagination)


@router.get("/my/enrolled", response_model=PaginatedResponse)
def get_my_enrolled_subjects(
    pagination: PaginationParams = Depends(),
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db)
):
    """جلب المواد التي سجل فيها الطالب الحالي"""
    enrollments = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_student.id,
        models.Enrollment.is_deleted == False,
        models.Enrollment.status == "active"
    ).all()
    subject_ids = [e.subject_id for e in enrollments]
    query = db.query(models.Subject).filter(models.Subject.id.in_(subject_ids), models.Subject.is_deleted == False) if subject_ids else db.query(models.Subject).filter(False)
    return paginate_query(query.order_by(models.Subject.created_at.desc()), pagination)


@router.get("/my/taught", response_model=Optional[schemas.SubjectResponse])
def get_my_taught_subject(
    current_teacher: models.User = Depends(auth.get_current_teacher),
    db: Session = Depends(get_db)
):
    """جلب المادة التي يدرسها المعلم الحالي"""
    link = db.query(models.TeacherSubject).filter(
        models.TeacherSubject.teacher_id == current_teacher.id,
        models.TeacherSubject.is_deleted == False,
    ).first()
    subject_id = link.subject_id if link else current_teacher.subject_id
    if current_teacher.role != "teacher" or not subject_id:
        return None
    return db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()


@router.get("/{subject_id}/stats")
def get_subject_stats(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
    return {
        "enrollments": db.query(models.Enrollment).filter(models.Enrollment.subject_id == subject_id, models.Enrollment.is_deleted == False).count(),
        "active_enrollments": db.query(models.Enrollment).filter(models.Enrollment.subject_id == subject_id, models.Enrollment.status == "active", models.Enrollment.is_deleted == False).count(),
        "lectures": db.query(models.Lecture).filter(models.Lecture.subject_id == subject_id, models.Lecture.is_deleted == False).count(),
        "homeworks": db.query(models.Homework).filter(models.Homework.subject_id == subject_id, models.Homework.is_deleted == False).count(),
        "teachers": db.query(models.TeacherSubject).filter(models.TeacherSubject.subject_id == subject_id, models.TeacherSubject.is_deleted == False).count(),
    }


@router.get("/{subject_id}", response_model=schemas.SubjectResponse)
def get_subject_details(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
    return subject


@router.post("", response_model=schemas.SubjectResponse)
def create_subject(
    subject_in: schemas.SubjectCreate,
    current_owner: models.User = Depends(require("can_edit_subject")),
    db: Session = Depends(get_db)
):
    """إنشاء مادة جديدة (المالك فقط)"""
    existing = db.query(models.Subject).filter(
        models.Subject.name == subject_in.name,
        models.Subject.grade_level == subject_in.grade_level,
        models.Subject.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="هذه المادة موجودة بالفعل لهذا الصف")
    new_subject = models.Subject(
        name=subject_in.name,
        grade_level=subject_in.grade_level,
        description=subject_in.description,
        category=subject_in.category,
        grade=subject_in.grade,
        semester=subject_in.semester,
        thumbnail=subject_in.thumbnail,
        max_students=subject_in.max_students,
    )
    db.add(new_subject)
    write_audit_log(db, action="create_subject", actor_id=current_owner.id, target_type="subject")
    db.commit()
    db.refresh(new_subject)
    return new_subject


@router.put("/{subject_id}", response_model=schemas.SubjectResponse)
def update_subject(
    subject_id: int,
    subject_in: schemas.SubjectCreate,
    current_owner: models.User = Depends(require("can_edit_subject")),
    db: Session = Depends(get_db)
):
    """تعديل مادة (المالك فقط)"""
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
        
    subject.name = subject_in.name
    subject.grade_level = subject_in.grade_level
    subject.description = subject_in.description
    subject.category = subject_in.category
    subject.grade = subject_in.grade
    subject.semester = subject_in.semester
    subject.thumbnail = subject_in.thumbnail
    subject.max_students = subject_in.max_students
    write_audit_log(db, action="update_subject", actor_id=current_owner.id, target_type="subject", target_id=subject.id)
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}")
def delete_subject(
    subject_id: int,
    current_owner: models.User = Depends(require("can_edit_subject")),
    db: Session = Depends(get_db)
):
    """حذف مادة (المالك فقط)"""
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
        
    subject.is_deleted = True
    subject.deleted_at = now_utc()
    subject.deleted_by = current_owner.id
    write_audit_log(db, action="delete_subject", actor_id=current_owner.id, target_type="subject", target_id=subject.id)
    db.commit()
    return {"message": "تم حذف المادة بنجاح"}


@router.post("/{subject_id}/enroll")
def enroll_subject(
    subject_id: int,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db)
):
    """تسجيل الطالب في مادة"""
    # التحقق من وجود المادة
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة غير موجودة")
        
    # التحقق من أن الطالب غير مسجل مسبقاً
    existing_enrollment = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_student.id,
        models.Enrollment.subject_id == subject_id,
        models.Enrollment.is_deleted == False
    ).first()
    
    if existing_enrollment:
        raise HTTPException(status_code=400, detail="أنت مسجل بالفعل في هذه المادة")
        
    # إنشاء التسجيل الجديد
    enrollment = models.Enrollment(student_id=current_student.id, subject_id=subject_id, status="active")
    db.add(enrollment)
    
    # إضافة إشعار
    notification = models.Notification(
        user_id=current_student.id,
        title="تسجيل ناجح",
        message=f"تم تسجيلك بنجاح في مادة: {subject.name}",
        type="system"
    )
    db.add(notification)
    db.commit()
    
    return {"message": f"تم التسجيل بنجاح في مادة {subject.name}"}


@router.post("/{subject_id}/unenroll")
def unenroll_subject(
    subject_id: int,
    current_student: models.User = Depends(auth.get_current_student),
    db: Session = Depends(get_db)
):
    """إلغاء تسجيل الطالب من المادة"""
    enrollment = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_student.id,
        models.Enrollment.subject_id == subject_id,
        models.Enrollment.is_deleted == False
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=400, detail="أنت غير مسجل في هذه المادة أساساً")
        
    enrollment.status = "cancelled"
    enrollment.is_deleted = True
    enrollment.deleted_at = now_utc()
    enrollment.deleted_by = current_student.id
    db.commit()
    return {"message": "تم إلغاء تسجيلك من المادة بنجاح"}


@router.post("/{subject_id}/prerequisites")
def add_subject_prerequisite(
    subject_id: int,
    payload: schemas.SubjectPrerequisiteCreate,
    current_owner: models.User = Depends(require("can_edit_subject")),
    db: Session = Depends(get_db),
):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.is_deleted == False).first()
    prerequisite = db.query(models.Subject).filter(
        models.Subject.id == payload.prerequisite_subject_id,
        models.Subject.is_deleted == False,
    ).first()
    if not subject or not prerequisite:
        raise HTTPException(status_code=404, detail="المادة أو المتطلب غير موجود")
    if subject_id == payload.prerequisite_subject_id:
        raise HTTPException(status_code=400, detail="لا يمكن أن تكون المادة متطلباً لنفسها")
    existing = db.query(models.SubjectPrerequisite).filter(
        models.SubjectPrerequisite.subject_id == subject_id,
        models.SubjectPrerequisite.prerequisite_subject_id == payload.prerequisite_subject_id,
        models.SubjectPrerequisite.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="المتطلب موجود بالفعل")
    row = models.SubjectPrerequisite(subject_id=subject_id, prerequisite_subject_id=payload.prerequisite_subject_id)
    db.add(row)
    write_audit_log(db, action="add_subject_prerequisite", actor_id=current_owner.id, target_type="subject", target_id=subject_id)
    db.commit()
    return {"message": "تمت إضافة المتطلب بنجاح"}


@router.get("/{subject_id}/prerequisites")
def get_subject_prerequisites(subject_id: int, db: Session = Depends(get_db)):
    rows = db.query(models.SubjectPrerequisite).filter(
        models.SubjectPrerequisite.subject_id == subject_id,
        models.SubjectPrerequisite.is_deleted == False,
    ).all()
    return [{"id": row.id, "subject": row.prerequisite_subject} for row in rows]
