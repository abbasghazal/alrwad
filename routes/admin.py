import random
import string
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from database import get_db
from email_service import EmailDeliveryError, EmailService, verification_email
import models
import schemas
import auth
from permissions.dependencies import require
from services.audit import write_audit_log
from services.notifications import create_notification
from utils import PaginatedResponse, PaginationParams, now_utc, paginate_query

router = APIRouter(prefix="/admin", tags=["لوحة المالك والإشراف"])

@router.get("/stats")
def get_platform_stats(
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db)
):
    """جلب إحصائيات المنصة الكلية لتعرض في لوحة المالك"""
    total_users = db.query(models.User).filter(models.User.is_deleted == False).count()
    total_students = db.query(models.User).filter(models.User.role == "student", models.User.is_deleted == False).count()
    total_teachers = db.query(models.User).filter(models.User.role == "teacher", models.User.is_deleted == False).count()
    total_tutors = db.query(models.User).filter(models.User.role == "tutor", models.User.is_deleted == False).count()
    total_subjects = db.query(models.Subject).filter(models.Subject.is_deleted == False).count()
    total_lectures = db.query(models.Lecture).filter(models.Lecture.is_deleted == False).count()
    total_homeworks = db.query(models.Homework).filter(models.Homework.is_deleted == False).count()
    total_submissions = db.query(models.Submission).filter(models.Submission.is_deleted == False).count()
    total_ratings = db.query(models.Rating).filter(models.Rating.is_deleted == False).count()
    
    # جلب نشاط المنصة الأخير (أحدث التسجيلات، الواجبات المسلمة، المحاضرات)
    recent_users = db.query(models.User).filter(models.User.is_deleted == False).order_by(models.User.created_at.desc()).limit(5).all()
    recent_submissions = db.query(models.Submission).filter(models.Submission.is_deleted == False).order_by(models.Submission.submitted_at.desc()).limit(5).all()
    recent_ratings = db.query(models.Rating).filter(models.Rating.is_deleted == False).order_by(models.Rating.created_at.desc()).limit(5).all()
    recent_audits = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(5).all()
    
    # تنسيق النشاطات الأخيرة
    activities = []
    for u in recent_users:
        role_map = {"student": "طالب", "teacher": "مدرس", "owner": "مالك", "tutor": "مدرس خصوصي"}
        activities.append({
            "type": "user_register",
            "message": f"انضم مستخدم جديد: {u.first_name} {u.last_name} ({role_map.get(u.role, u.role)})",
            "time": u.created_at.isoformat()
        })
        
    for s in recent_submissions:
        if not s.student or not s.homework:
            continue
        activities.append({
            "type": "homework_submit",
            "message": f"سلم الطالب {s.student.first_name} {s.student.last_name} واجب '{s.homework.title}'",
            "time": s.submitted_at.isoformat()
        })
        
    for r in recent_ratings:
        if not r.teacher or not r.student:
            continue
        activities.append({
            "type": "teacher_rate",
            "message": f"تم تقييم المعلم {r.teacher.first_name} بـ {r.stars} نجوم من قبل {r.student.first_name}",
            "time": r.created_at.isoformat()
        })

    for audit in recent_audits:
        activities.append({
            "type": "audit",
            "message": f"نشاط إداري: {audit.action}",
            "time": audit.created_at.isoformat(),
        })
        
    # ترتيب النشاطات حسب الأحدث تنازلياً
    activities = sorted(activities, key=lambda x: x["time"], reverse=True)[:10]
    
    growth_rows = db.query(
        func.date_trunc("month", models.User.created_at).label("month"),
        models.User.role,
        func.count(models.User.id).label("count"),
    ).filter(models.User.is_deleted == False).group_by("month", models.User.role).order_by("month").all()
    growth_by_month = {}
    for row in growth_rows:
        label = row.month.strftime("%Y-%m") if row.month else "unknown"
        growth_by_month.setdefault(label, {"month": label, "students": 0, "teachers": 0})
        if row.role == "student":
            growth_by_month[label]["students"] = row.count
        if row.role in ("teacher", "tutor"):
            growth_by_month[label]["teachers"] += row.count
    growth_stats = list(growth_by_month.values())

    return {
        "counts": {
            "total_users": total_users,
            "students": total_students,
            "teachers": total_teachers,
            "tutors": total_tutors,
            "subjects": total_subjects,
            "lectures": total_lectures,
            "homeworks": total_homeworks,
            "submissions": total_submissions,
            "ratings": total_ratings
        },
        "activities": activities,
        "growth": growth_stats
    }


@router.get("/reports/education")
def get_education_report(
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    """تقرير تعليمي مختصر للمالك: تسجيلات، حضور، تسليمات، ودرجات."""
    active_enrollments = db.query(models.Enrollment).filter(
        models.Enrollment.status == "active",
        models.Enrollment.is_deleted == False,
    ).count()
    submitted_homeworks = db.query(models.Submission).filter(models.Submission.is_deleted == False).count()
    graded_homeworks = db.query(models.Submission).filter(
        models.Submission.grade.isnot(None),
        models.Submission.is_deleted == False,
    ).count()
    late_homeworks = db.query(models.Submission).filter(
        models.Submission.status == "late",
        models.Submission.is_deleted == False,
    ).count()
    attendance_rows = db.query(
        models.LectureAttendance.status,
        func.count(models.LectureAttendance.id).label("count"),
    ).filter(models.LectureAttendance.is_deleted == False).group_by(models.LectureAttendance.status).all()
    attendance = {row.status: row.count for row in attendance_rows}
    top_subjects = db.query(
        models.Subject.id,
        models.Subject.name,
        func.count(models.Enrollment.id).label("students"),
    ).join(models.Enrollment, models.Enrollment.subject_id == models.Subject.id).filter(
        models.Subject.is_deleted == False,
        models.Enrollment.is_deleted == False,
    ).group_by(models.Subject.id, models.Subject.name).order_by(func.count(models.Enrollment.id).desc()).limit(10).all()
    return {
        "active_enrollments": active_enrollments,
        "submitted_homeworks": submitted_homeworks,
        "graded_homeworks": graded_homeworks,
        "late_homeworks": late_homeworks,
        "attendance": attendance,
        "top_subjects": [
            {"id": row.id, "name": row.name, "students": row.students}
            for row in top_subjects
        ],
    }


@router.get("/reports/finance")
def get_finance_report(
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    """تقرير مالي مبني على عمليات المحفظة الحالية."""
    rows = db.query(
        models.WalletTransaction.type,
        models.WalletTransaction.status,
        func.coalesce(func.sum(models.WalletTransaction.amount), 0).label("amount"),
        func.count(models.WalletTransaction.id).label("count"),
    ).filter(models.WalletTransaction.is_deleted == False).group_by(
        models.WalletTransaction.type,
        models.WalletTransaction.status,
    ).all()
    by_status = {}
    by_type = {}
    for row in rows:
        amount = round(float(row.amount or 0), 2)
        by_status[row.status] = round(by_status.get(row.status, 0) + amount, 2)
        by_type.setdefault(row.type, {"amount": 0, "count": 0})
        by_type[row.type]["amount"] = round(by_type[row.type]["amount"] + amount, 2)
        by_type[row.type]["count"] += row.count
    return {
        "by_status": by_status,
        "by_type": by_type,
        "paid_bookings": db.query(models.TutorBooking).filter(
            models.TutorBooking.payment_status == "paid",
            models.TutorBooking.is_deleted == False,
        ).count(),
        "unpaid_bookings": db.query(models.TutorBooking).filter(
            models.TutorBooking.payment_status.in_(["unpaid", "pending", "review"]),
            models.TutorBooking.is_deleted == False,
        ).count(),
    }


@router.get("/audit-logs", response_model=PaginatedResponse)
def get_audit_logs(
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action.ilike(f"%{action}%"))
    if target_type:
        query = query.filter(models.AuditLog.target_type == target_type)
    return paginate_query(query.order_by(models.AuditLog.created_at.desc()), pagination)


@router.post("/notifications/broadcast")
def broadcast_notification(
    payload: schemas.BroadcastNotificationCreate,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    query = db.query(models.User).filter(
        models.User.is_deleted == False,
        models.User.is_blocked == False,
    )
    if payload.role:
        query = query.filter(models.User.role == payload.role)
    users = query.all()
    for user in users:
        create_notification(
            db,
            user.id,
            payload.title,
            payload.message,
            "broadcast",
            send_email=payload.send_email,
        )
    write_audit_log(
        db,
        action="broadcast_notification",
        actor_id=current_owner.id,
        target_type="notification",
        details=f"role={payload.role or 'all'};count={len(users)}",
    )
    db.commit()
    return {"message": "تم إرسال التنبيه الجماعي", "recipients": len(users)}


@router.post("/email/test")
@router.post("/smtp/test")
def test_email_delivery(
    payload: schemas.EmailTestRequest,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    service = EmailService()
    if not service.is_configured:
        missing = ", ".join(service.config_errors) or "Email API settings"
        raise HTTPException(status_code=503, detail=f"Email API غير مهيأ. الحقول الناقصة: {missing}")
    to_email = str(payload.to_email or current_owner.email)
    try:
        service.send_html(to_email, "Email API Test - Alrwad", verification_email("123456"))
    except EmailDeliveryError as exc:
        write_audit_log(db, action="email_test_failed", actor_id=current_owner.id, target_type="email", details=f"phase={exc.phase};error={exc}")
        db.commit()
        raise HTTPException(status_code=503, detail=f"فشل اختبار Email API في مرحلة {exc.phase}: {exc}") from exc
    write_audit_log(db, action="email_test_passed", actor_id=current_owner.id, target_type="email", details=f"to={to_email}")
    db.commit()
    return {"message": "تم إرسال رسالة اختبار البريد بنجاح", "to_email": to_email}


@router.get("/users", response_model=PaginatedResponse)
def get_all_users(
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db)
):
    """عرض قائمة بجميع المستخدمين مع إمكانية البحث والتصفية (المالك فقط)"""
    query = db.query(models.User).filter(models.User.is_deleted == False)
    if role:
        query = query.filter(models.User.role == role)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.User.first_name.like(search_filter)) |
            (models.User.last_name.like(search_filter)) |
            (models.User.username.like(search_filter)) |
            (models.User.email.like(search_filter))
        )
    return paginate_query(query.order_by(models.User.created_at.desc()), pagination)


@router.post("/users/{user_id}/block")
def toggle_block_user(
    user_id: int,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db)
):
    """حظر أو إلغاء حظر حساب مستخدم (المالك فقط)"""
    user = db.query(models.User).filter(models.User.id == user_id, models.User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
        
    if user.id == current_owner.id:
        raise HTTPException(status_code=400, detail="لا يمكنك حظر حسابك الشخصي")
        
    user.is_blocked = not user.is_blocked
    db.add(models.UserActivity(user_id=user.id, action="status_change", details=f"blocked={user.is_blocked};changed_by={current_owner.id}"))
    write_audit_log(db, action="block_user" if user.is_blocked else "unblock_user", actor_id=current_owner.id, target_type="user", target_id=user.id)
    db.commit()
    status_str = "محظور" if user.is_blocked else "نشط"
    return {"message": f"تم تغيير حالة المستخدم بنجاح إلى: {status_str}", "is_blocked": user.is_blocked}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db)
):
    """حذف حساب مستخدم بشكل نهائي من قبل الإدارة"""
    user = db.query(models.User).filter(models.User.id == user_id, models.User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
        
    if user.id == current_owner.id:
        raise HTTPException(status_code=400, detail="لا يمكنك حذف حسابك الشخصي")
        
    user.is_deleted = True
    user.deleted_at = now_utc()
    user.deleted_by = current_owner.id
    write_audit_log(db, action="delete_user", actor_id=current_owner.id, target_type="user", target_id=user.id)
    db.commit()
    return {"message": "تم حذف حساب المستخدم وجميع بياناته بنجاح"}


@router.post("/codes", response_model=schemas.TeacherCodeResponse)
def generate_teacher_code(
    payload: schemas.TeacherCodeCreate,
    current_owner: models.User = Depends(require("can_edit_subject")),
    db: Session = Depends(get_db)
):
    """توليد كود تسجيل جديد لمدرس لمادة محددة (المالك فقط)"""
    # التحقق من وجود المادة
    subject = db.query(models.Subject).filter(models.Subject.id == payload.subject_id, models.Subject.is_deleted == False).first()
    if not subject:
        raise HTTPException(status_code=404, detail="المادة المحددة غير موجودة")
        
    # توليد كود فريد من 6 أحرف كبيرة وأرقام
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # التأكد من عدم تكراره
    while db.query(models.TeacherCode).filter(models.TeacherCode.code == code).first():
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
    expires_at = now_utc() + timedelta(days=payload.expires_in_days)
    
    code_entry = models.TeacherCode(
        code=code,
        subject_id=payload.subject_id,
        is_used=False,
        expires_at=expires_at
    )
    
    db.add(code_entry)
    write_audit_log(db, action="generate_teacher_code", actor_id=current_owner.id, target_type="subject", target_id=payload.subject_id)
    db.commit()
    db.refresh(code_entry)
    return code_entry


@router.get("/codes", response_model=PaginatedResponse)
def get_teacher_codes(
    pagination: PaginationParams = Depends(),
    current_owner: models.User = Depends(require("can_edit_subject")),
    db: Session = Depends(get_db)
):
    """عرض جميع أكواد المدرسين المنشأة وحالة استخدامها (المالك فقط)"""
    return paginate_query(db.query(models.TeacherCode).order_by(models.TeacherCode.created_at.desc()), pagination)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """جلب إعدادات المنصة العامة (متاحة للجميع لتهيئة الواجهة)"""
    settings = db.query(models.Setting).all()
    settings_dict = {s.key: s.value for s in settings}
    
    # الإعدادات الافتراضية
    default_settings = {
        "platform_name": "أكاديمية الرواد",
        "contact_email": "info@alrwad.edu",
        "about_text": "منصة تعليمية رائدة تجمع الطلاب والمدرسين الخصوصيين في مكان واحد باللغة العربية.",
        "phone": "+966500000000",
        "facebook_url": "https://facebook.com",
        "twitter_url": "https://twitter.com"
    }
    
    for k, v in default_settings.items():
        if k not in settings_dict:
            settings_dict[k] = v
            
    return settings_dict


@router.post("/settings")
def update_settings(
    payload: dict = Body(...),
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db)
):
    """تحديث إعدادات المنصة (المالك فقط)"""
    for k, v in payload.items():
        setting = db.query(models.Setting).filter(models.Setting.key == k).first()
        if setting:
            setting.value = str(v)
        else:
            db.add(models.Setting(key=k, value=str(v)))
    write_audit_log(db, action="update_settings", actor_id=current_owner.id, target_type="settings")
    db.commit()
    return {"message": "تم حفظ الإعدادات بنجاح"}


@router.get("/sections", response_model=PaginatedResponse)
def get_sections(
    grade_level: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
):
    query = db.query(models.GradeSection).filter(models.GradeSection.is_deleted == False)
    if grade_level:
        query = query.filter(models.GradeSection.grade_level == grade_level)
    return paginate_query(query.order_by(models.GradeSection.grade_level.asc(), models.GradeSection.name.asc()), pagination)


@router.post("/sections", response_model=schemas.GradeSectionResponse)
def create_section(
    payload: schemas.GradeSectionCreate,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    existing = db.query(models.GradeSection).filter(
        models.GradeSection.grade_level == payload.grade_level,
        models.GradeSection.name == payload.name,
        models.GradeSection.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="هذه الشعبة موجودة بالفعل لهذا الصف")
    section = models.GradeSection(
        grade_level=payload.grade_level,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(section)
    write_audit_log(db, action="create_grade_section", actor_id=current_owner.id, target_type="grade_section")
    db.commit()
    db.refresh(section)
    return section


@router.delete("/sections/{section_id}")
def delete_section(
    section_id: int,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    section = db.query(models.GradeSection).filter(models.GradeSection.id == section_id, models.GradeSection.is_deleted == False).first()
    if not section:
        raise HTTPException(status_code=404, detail="الشعبة غير موجودة")
    section.is_deleted = True
    section.deleted_at = now_utc()
    section.deleted_by = current_owner.id
    write_audit_log(db, action="delete_grade_section", actor_id=current_owner.id, target_type="grade_section", target_id=section.id)
    db.commit()
    return {"message": "تم حذف الشعبة بنجاح"}


@router.get("/groups", response_model=PaginatedResponse)
def get_groups(
    section_id: Optional[int] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
):
    query = db.query(models.SectionGroup).filter(models.SectionGroup.is_deleted == False)
    if section_id:
        query = query.filter(models.SectionGroup.section_id == section_id)
    return paginate_query(query.order_by(models.SectionGroup.section_id.asc(), models.SectionGroup.name.asc()), pagination)


@router.post("/groups", response_model=schemas.SectionGroupResponse)
def create_group(
    payload: schemas.SectionGroupCreate,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    section = db.query(models.GradeSection).filter(models.GradeSection.id == payload.section_id, models.GradeSection.is_deleted == False).first()
    if not section:
        raise HTTPException(status_code=404, detail="الشعبة غير موجودة")
    existing = db.query(models.SectionGroup).filter(
        models.SectionGroup.section_id == payload.section_id,
        models.SectionGroup.name == payload.name,
        models.SectionGroup.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="هذه المجموعة موجودة بالفعل داخل الشعبة")
    group = models.SectionGroup(
        section_id=payload.section_id,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(group)
    write_audit_log(db, action="create_section_group", actor_id=current_owner.id, target_type="section_group")
    db.commit()
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: int,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    group = db.query(models.SectionGroup).filter(models.SectionGroup.id == group_id, models.SectionGroup.is_deleted == False).first()
    if not group:
        raise HTTPException(status_code=404, detail="المجموعة غير موجودة")
    group.is_deleted = True
    group.deleted_at = now_utc()
    group.deleted_by = current_owner.id
    write_audit_log(db, action="delete_section_group", actor_id=current_owner.id, target_type="section_group", target_id=group.id)
    db.commit()
    return {"message": "تم حذف المجموعة بنجاح"}
