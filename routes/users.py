import os
import uuid
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import Optional, Tuple
from database import get_db
import models
import schemas
import auth
from permissions.dependencies import require
from security.password_policy import validate_password_strength
from services.audit import write_audit_log
from utils import PaginatedResponse, PaginationParams, now_utc, paginate_query, safe_delete_static_file, upload_subdir_path, upload_url

router = APIRouter(prefix="/users", tags=["إدارة الحسابات والملفات الشخصية"])

AVATAR_DIR = upload_subdir_path("avatars")
ALLOWED_AVATAR_MIME_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024


def normalize_avatar(file: UploadFile) -> Tuple[bytes, str]:
    if file.content_type not in ALLOWED_AVATAR_MIME_TYPES:
        raise HTTPException(status_code=400, detail="نوع الملف غير مسموح به. الصيغ المتاحة: JPEG, PNG, WEBP")

    raw = file.file.read(MAX_AVATAR_SIZE_BYTES + 1)
    file.file.seek(0)
    if len(raw) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="حجم الصورة يتجاوز الحد المسموح 2MB")
    if raw.startswith(b"MZ") or b"<?php" in raw[:512] or b"<script" in raw[:1024].lower():
        raise HTTPException(status_code=400, detail="محتوى الملف غير آمن")

    try:
        from PIL import Image
    except ImportError:
        return raw, ALLOWED_AVATAR_MIME_TYPES[file.content_type]

    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        image = image.convert("RGB")
        image.thumbnail((512, 512))
        output = BytesIO()
        image.save(output, format="WEBP", quality=82, method=6)
        return output.getvalue(), ".webp"
    except Exception:
        raise HTTPException(status_code=400, detail="ملف الصورة غير صالح")

@router.put("/profile", response_model=schemas.UserResponse)
def update_profile(
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """تحديث البيانات الشخصية"""
    if payload.username:
        username = payload.username.strip().lower()
        existing = db.query(models.User).filter(models.User.username == username, models.User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="اسم المستخدم المدخل قيد الاستخدام")
        current_user.username = username

    if payload.email and payload.email.lower() != current_user.email:
        email = payload.email.lower()
        # التحقق من عدم استخدام البريد الإلكتروني الجديد
        existing = db.query(models.User).filter(models.User.email == email, models.User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="البريد الإلكتروني المدخل قيد الاستخدام")
        current_user.email = email
        current_user.is_verified = False
        
    if payload.first_name:
        current_user.first_name = payload.first_name
    if payload.last_name:
        current_user.last_name = payload.last_name
    if payload.phone is not None:
        current_user.phone = payload.phone
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    if payload.bio is not None:
        current_user.bio = payload.bio

    db.add(models.UserActivity(user_id=current_user.id, action="profile_update"))
    write_audit_log(db, action="profile_update", actor_id=current_user.id, target_type="user", target_id=current_user.id)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    payload: schemas.UserPasswordChange,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """تغيير كلمة المرور الشخصية"""
    if not auth.verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")
    if payload.new_password_confirm and payload.new_password != payload.new_password_confirm:
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة وتأكيدها غير متطابقين")

    validate_password_strength(payload.new_password)
    current_user.password_hash = auth.get_password_hash(payload.new_password)
    db.query(models.UserSession).filter(models.UserSession.user_id == current_user.id).update({"is_revoked": True})
    db.add(models.UserActivity(user_id=current_user.id, action="password_change"))
    db.commit()
    return {"message": "تم تغيير كلمة المرور بنجاح"}


@router.post("/avatar")
def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """رفع وتغيير الصورة الشخصية"""
    content, file_ext = normalize_avatar(file)
    filename = f"{uuid.uuid4()}{file_ext}"
    filepath = os.path.join(AVATAR_DIR, filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(content)
        
    # حذف الصورة القديمة محلياً
    if current_user.avatar_url:
        safe_delete_static_file(current_user.avatar_url, "uploads/avatars/")
                
    current_user.avatar_url = upload_url("avatars", filename)
    db.add(models.UserActivity(user_id=current_user.id, action="avatar_update"))
    write_audit_log(db, action="avatar_update", actor_id=current_user.id, target_type="user", target_id=current_user.id)
    db.commit()
    return {"message": "تم تحديث الصورة الشخصية بنجاح", "avatar_url": current_user.avatar_url}


@router.delete("/delete-account")
def delete_account(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """حذف الحساب بنظام soft delete"""
    # لا يمكن حذف حساب المالك لحماية المنصة
    if current_user.role == "owner":
        raise HTTPException(status_code=400, detail="لا يمكن حذف حساب مالك المنصة الأساسي")
        
    current_user.is_deleted = True
    current_user.deleted_at = now_utc()
    current_user.deleted_by = current_user.id
    db.query(models.UserSession).filter(models.UserSession.user_id == current_user.id).update({"is_revoked": True})
    write_audit_log(db, action="delete_account", actor_id=current_user.id, target_type="user", target_id=current_user.id)
    db.commit()
    return {"message": "تم تعطيل حسابك وحفظ سجل الحذف بنجاح"}


@router.get("/search", response_model=PaginatedResponse)
def search_users(
    q: str = Query("", min_length=0),
    role: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    query = db.query(models.User).filter(models.User.is_deleted == False)
    if role:
        query = query.filter(models.User.role == role)
    if q:
        search_filter = f"%{q.lower()}%"
        query = query.filter(
            (models.User.first_name.ilike(search_filter)) |
            (models.User.last_name.ilike(search_filter)) |
            (models.User.username.ilike(search_filter)) |
            (models.User.email.ilike(search_filter))
        )
    return paginate_query(query.order_by(models.User.created_at.desc()), pagination)


@router.get("/activity", response_model=PaginatedResponse)
def get_user_activity(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.UserActivity).filter(models.UserActivity.user_id == current_user.id).order_by(models.UserActivity.created_at.desc())
    return paginate_query(query, pagination)


@router.get("/{user_id}/stats")
def get_user_stats(
    user_id: int,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id, models.User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    return {
        "enrollments": db.query(models.Enrollment).filter(models.Enrollment.student_id == user_id, models.Enrollment.is_deleted == False).count(),
        "submissions": db.query(models.Submission).filter(models.Submission.student_id == user_id, models.Submission.is_deleted == False).count(),
        "ratings_given": db.query(models.Rating).filter(models.Rating.student_id == user_id, models.Rating.is_deleted == False).count(),
        "ratings_received": db.query(models.Rating).filter(models.Rating.teacher_id == user_id, models.Rating.is_deleted == False).count(),
        "sessions": db.query(models.UserSession).filter(models.UserSession.user_id == user_id, models.UserSession.is_revoked == False).count(),
    }


@router.patch("/status")
def update_user_status(
    payload: schemas.UserStatusUpdate,
    current_owner: models.User = Depends(require("can_manage_users")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == payload.user_id, models.User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if user.id == current_owner.id:
        raise HTTPException(status_code=400, detail="لا يمكنك تعديل حالة حسابك من هنا")
    if payload.is_blocked is not None:
        user.is_blocked = payload.is_blocked
    if payload.role is not None:
        user.role = payload.role
        db.add(models.UserActivity(user_id=user.id, action="role_change", details=f"changed_by={current_owner.id}"))
    if payload.permissions is not None:
        user.permissions = payload.permissions
        db.add(models.UserActivity(user_id=user.id, action="permissions_change", details=f"changed_by={current_owner.id}"))
    write_audit_log(db, action="user_status_update", actor_id=current_owner.id, target_type="user", target_id=user.id)
    db.commit()
    return {"message": "تم تحديث حالة المستخدم", "is_blocked": user.is_blocked, "role": user.role}


@router.get("/notifications", response_model=PaginatedResponse)
def get_notifications(
    pagination: PaginationParams = Depends(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """جلب تنبيهات المستخدم الحالي"""
    query = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    ).order_by(models.Notification.created_at.desc())
    return paginate_query(query, pagination)


@router.post("/notifications/read")
def mark_notifications_as_read(
    notification_id: Optional[int] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """تعليم التنبيهات كمقروءة (تنبيه محدد أو الكل)"""
    query = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    )
    if notification_id:
        query = query.filter(models.Notification.id == notification_id)
        
    query.update({"is_read": True})
    db.commit()
    return {"message": "تم تحديث حالة التنبيهات بنجاح"}
