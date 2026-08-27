import random
import string
import logging
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
import auth
from email_service import EmailDeliveryError, EmailService, reset_password_email, verification_email
from security.password_policy import validate_password_strength
from security.rate_limit import enforce_rate_limit
from services.audit import write_audit_log
from utils import ensure_aware_utc, now_utc

router = APIRouter(prefix="/auth", tags=["التوثيق"])
logger = logging.getLogger(__name__)


def generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def log_activity(db: Session, user_id: int, action: str, request: Request, details: Optional[str] = None) -> None:
    db.add(
        models.UserActivity(
            user_id=user_id,
            action=action,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details=details,
        )
    )


def send_required_email(to_email: str, subject: str, html_body: str, strict: bool = False) -> bool:
    email_service = EmailService()
    if not email_service.is_configured:
        missing = "، ".join(email_service.config_errors) or "إعدادات Email API"
        message = f"إرسال البريد الإلكتروني غير مهيأ. يرجى ضبط: {missing}"
        if strict:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
        logger.warning("%s", message)
        return False
    try:
        email_service.send_html(to_email, subject, html_body)
        return True
    except EmailDeliveryError as exc:
        logger.exception("Email API send failed for %s during %s: %s", to_email, exc.phase, exc)
        if strict:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"تعذر إرسال البريد الإلكتروني. سبب الفشل في السجل: {exc.phase}.",
            ) from exc
        return False
    except Exception as exc:
        logger.exception("Email API send failed for %s: %s", to_email, exc)
        if strict:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="تعذر إرسال البريد الإلكتروني. تحقق من إعدادات Email API.",
            ) from exc
        return False


@router.post("/register", response_model=schemas.UserResponse)
def register(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    validate_password_strength(user_in.password)
    username = user_in.username.strip().lower()
    email = user_in.email.lower()
    # التحقق من أن اسم المستخدم غير مكرر
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="اسم المستخدم مسجل بالفعل"
        )
    
    # التحقق من أن البريد الإلكتروني غير مكرر
    db_email = db.query(models.User).filter(models.User.email == email).first()
    if db_email:
        raise HTTPException(
            status_code=400,
            detail="البريد الإلكتروني مسجل بالفعل"
        )
    
    # التحقق من صلاحيات المدرس
    code_entry = None
    if user_in.role == "teacher":
        if not user_in.subject_id:
            raise HTTPException(status_code=400, detail="يجب تحديد المادة التي ستدرسها")
        if not user_in.teacher_code:
            raise HTTPException(status_code=400, detail="يجب إدخال كود المادة الخاص بالتسجيل")
        
        # التحقق من صحة كود المادة وصلاحيته
        code_entry = db.query(models.TeacherCode).filter(
            models.TeacherCode.code == user_in.teacher_code,
            models.TeacherCode.subject_id == user_in.subject_id
        ).first()
        
        if not code_entry:
            raise HTTPException(status_code=400, detail="كود التسجيل المدخل غير صحيح لهذه المادة")
        if code_entry.is_used:
            raise HTTPException(status_code=400, detail="هذا الكود تم استخدامه مسبقاً")
        if ensure_aware_utc(code_entry.expires_at) < now_utc():
            raise HTTPException(status_code=400, detail="كود التسجيل منتهي الصلاحية")
            
    elif user_in.role == "student":
        if not user_in.grade_level:
            raise HTTPException(status_code=400, detail="يجب تحديد الصف الدراسي للطالب")
        section = None
        if user_in.section_id:
            section = db.query(models.GradeSection).filter(
                models.GradeSection.id == user_in.section_id,
                models.GradeSection.grade_level == user_in.grade_level,
                models.GradeSection.is_deleted == False,
            ).first()
            if not section:
                raise HTTPException(status_code=400, detail="الشعبة لا تنتمي إلى الصف المحدد")
        if user_in.group_id:
            if not section:
                raise HTTPException(status_code=400, detail="يجب تحديد الشعبة قبل اختيار المجموعة")
            group = db.query(models.SectionGroup).filter(
                models.SectionGroup.id == user_in.group_id,
                models.SectionGroup.is_deleted == False,
            ).first()
            if not group or group.section_id != user_in.section_id:
                raise HTTPException(status_code=400, detail="المجموعة لا تنتمي إلى الشعبة المحددة")
            
    elif user_in.role == "tutor":
        if not user_in.specialty or user_in.hourly_rate is None:
            raise HTTPException(status_code=400, detail="يجب إدخال التخصص وسعر الساعة للمدرس الخصوصي")

    # تشفير كلمة المرور وحفظ الحساب
    hashed_password = auth.get_password_hash(user_in.password)
    verification_code = generate_code()
    
    new_user = models.User(
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        username=username,
        email=email,
        password_hash=hashed_password,
        role=user_in.role,
        grade_level=user_in.grade_level,
        section_id=user_in.section_id if user_in.role == "student" else None,
        group_id=user_in.group_id if user_in.role == "student" else None,
        subject_id=user_in.subject_id if user_in.role == "teacher" else None,
        specialty=user_in.specialty if user_in.role == "tutor" else None,
        hourly_rate=user_in.hourly_rate if user_in.role == "tutor" else None,
        is_verified=user_in.role == "owner",
        verification_code=verification_code,
        verification_expires_at=now_utc() + timedelta(minutes=10),
    )
    
    db.add(new_user)
    db.flush()

    if user_in.role == "teacher" and code_entry:
        code_entry.is_used = True
        code_entry.used_by_id = new_user.id
        db.add(models.TeacherSubject(teacher_id=new_user.id, subject_id=user_in.subject_id, is_assistant=False))

    db.commit()
    db.refresh(new_user)

    if not new_user.is_verified:
        send_required_email(
            new_user.email,
            "تفعيل البريد الإلكتروني - أكاديمية الرواد",
            verification_email(verification_code),
        )

    return new_user


@router.post("/login", response_model=schemas.Token)
def login(
    request: Request,
    username: str = Body(...),
    password: str = Body(...),
    db: Session = Depends(get_db)
):
    enforce_rate_limit(request, "login", limit=5, seconds=60)
    lookup = username.strip().lower()
    # البحث عن اسم المستخدم أو البريد الإلكتروني
    user = db.query(models.User).filter(
        (models.User.username == lookup) | (models.User.email == lookup)
    ).first()
    
    if user and user.locked_until and ensure_aware_utc(user.locked_until) > now_utc():
        raise HTTPException(status_code=423, detail="تم قفل الحساب مؤقتاً بسبب محاولات دخول خاطئة")

    if not user or not auth.verify_password(password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now_utc() + timedelta(minutes=15)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="اسم المستخدم أو كلمة المرور غير صحيحة",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="تم حظر حسابك من قبل الإدارة"
        )

    if not user.is_verified and user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="يجب تفعيل البريد الإلكتروني قبل تسجيل الدخول")
        
    # توليد التوكين
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = now_utc()
    request_ip = request.client.host if request.client else None
    previous_session = db.query(models.UserSession).filter(
        models.UserSession.user_id == user.id,
        models.UserSession.is_revoked == False,
    ).order_by(models.UserSession.last_activity.desc()).first()
    if previous_session and request_ip and previous_session.ip_address and previous_session.ip_address != request_ip:
        log_activity(db, user.id, "suspicious_login", request, details=f"previous_ip={previous_session.ip_address};new_ip={request_ip}")
        write_audit_log(db, action="suspicious_login", actor_id=user.id, target_type="user", target_id=user.id)
    refresh_token, session_id = auth.create_session(
        db,
        user,
        ip_address=request_ip,
        user_agent=request.headers.get("user-agent"),
    )
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role, "sid": session_id})
    log_activity(db, user.id, "login", request)
    write_audit_log(db, action="login", actor_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


# توافق مع Swagger (Form login)
@router.post("/login/swagger", response_model=schemas.Token)
def login_swagger(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    return login(request=request, username=form_data.username, password=form_data.password, db=db)


@router.post("/refresh", response_model=schemas.Token)
def refresh_token(payload: schemas.RefreshTokenRequest, db: Session = Depends(get_db)):
    token_hash = auth.hash_token(payload.refresh_token)
    session = db.query(models.UserSession).filter(models.UserSession.refresh_token_hash == token_hash).first()
    if not session or session.is_revoked or ensure_aware_utc(session.expires_at) < now_utc():
        raise HTTPException(status_code=401, detail="جلسة التحديث غير صالحة")
    user = session.user
    if user.is_blocked or user.is_deleted:
        raise HTTPException(status_code=403, detail="الحساب غير متاح")
    session.last_activity = now_utc()
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role, "sid": session.id})
    db.commit()
    return {"access_token": access_token, "refresh_token": payload.refresh_token, "token_type": "bearer"}


@router.post("/logout")
def logout(payload: schemas.RefreshTokenRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = auth.hash_token(payload.refresh_token)
    session = db.query(models.UserSession).filter(models.UserSession.refresh_token_hash == token_hash).first()
    if session:
        session.is_revoked = True
        log_activity(db, session.user_id, "logout", request)
        write_audit_log(db, action="logout", actor_id=session.user_id, target_type="session", target_id=session.id)
        db.commit()
    return {"message": "تم تسجيل الخروج بنجاح"}


@router.post("/logout-all")
def logout_all(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    db.query(models.UserSession).filter(models.UserSession.user_id == current_user.id).update({"is_revoked": True})
    db.commit()
    return {"message": "تم تسجيل الخروج من جميع الجلسات"}


@router.get("/sessions")
def get_sessions(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    sessions = db.query(models.UserSession).filter(models.UserSession.user_id == current_user.id).order_by(models.UserSession.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "ip_address": s.ip_address,
            "browser": s.browser,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "last_activity": s.last_activity,
            "is_revoked": s.is_revoked,
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    session = db.query(models.UserSession).filter(models.UserSession.id == session_id, models.UserSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
    session.is_revoked = True
    db.commit()
    return {"message": "تم إلغاء الجلسة"}


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.post("/reset-password-request")
def reset_password_request(
    payload: schemas.PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    enforce_rate_limit(request, "forgot_password", limit=5, seconds=300)
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user:
        return {"message": "إذا كان البريد مسجلاً، فستتلقى رمز الاستعادة"}
        
    # توليد رمز عشوائي من 6 أرقام
    code = generate_code()
    
    # تعطيل أي رموز قديمة لنفس المستخدم
    db.query(models.PasswordReset).filter(
        models.PasswordReset.user_id == user.id,
        models.PasswordReset.is_used == False
    ).update({"is_used": True})
    
    # حفظ الرمز الجديد
    reset_entry = models.PasswordReset(
        user_id=user.id,
        code=code,
        expires_at=now_utc() + timedelta(minutes=10),
        is_used=False
    )
    db.add(reset_entry)
    db.commit()
    send_required_email(
        user.email,
        "استعادة كلمة المرور",
        reset_password_email(code),
    )
    
    return {"message": "إذا كان البريد مسجلاً، فستتلقى رمز الاستعادة"}


@router.post("/forgot-password")
def forgot_password(
    payload: schemas.PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return reset_password_request(payload=payload, request=request, db=db)


@router.post("/verify-reset-code")
def verify_reset_code(payload: schemas.PasswordResetCodeVerify, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح أو منتهي الصلاحية")
    reset_entry = db.query(models.PasswordReset).filter(
        models.PasswordReset.user_id == user.id,
        models.PasswordReset.code == payload.code,
        models.PasswordReset.is_used == False
    ).first()
    if not reset_entry or ensure_aware_utc(reset_entry.expires_at) < now_utc():
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح أو منتهي الصلاحية")
    return {"message": "رمز التحقق صحيح"}


@router.post("/reset-password-verify")
def reset_password_verify(
    payload: schemas.PasswordResetVerify,
    db: Session = Depends(get_db)
):
    validate_password_strength(payload.new_password)
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني غير صحيح")

    if payload.new_password_confirm and payload.new_password != payload.new_password_confirm:
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة وتأكيدها غير متطابقين")
        
    # التحقق من صحة الكود وصلاحيته
    reset_entry = db.query(models.PasswordReset).filter(
        models.PasswordReset.user_id == user.id,
        models.PasswordReset.code == payload.code,
        models.PasswordReset.is_used == False
    ).first()
    
    if not reset_entry:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح أو تم استخدامه")
        
    if ensure_aware_utc(reset_entry.expires_at) < now_utc():
        raise HTTPException(status_code=400, detail="انتهت صلاحية رمز التحقق")
        
    # إعادة تعيين كلمة المرور
    user.password_hash = auth.get_password_hash(payload.new_password)
    reset_entry.is_used = True
    db.query(models.UserSession).filter(models.UserSession.user_id == user.id).update({"is_revoked": True})
    db.commit()
    
    return {"message": "تم إعادة تعيين كلمة المرور بنجاح، يمكنك الآن تسجيل الدخول"}


@router.post("/reset-password")
def reset_password(payload: schemas.PasswordResetVerify, db: Session = Depends(get_db)):
    return reset_password_verify(payload=payload, db=db)


@router.post("/verify-email")
def verify_email(payload: schemas.EmailVerifyRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or user.verification_code != payload.code:
        raise HTTPException(status_code=400, detail="رمز التفعيل غير صحيح")
    if not user.verification_expires_at or ensure_aware_utc(user.verification_expires_at) < now_utc():
        raise HTTPException(status_code=400, detail="انتهت صلاحية رمز التفعيل")
    user.is_verified = True
    user.verification_code = None
    user.verification_expires_at = None
    db.commit()
    return {"message": "تم تفعيل البريد الإلكتروني بنجاح"}


@router.post("/resend-code")
def resend_code(payload: schemas.PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if user and not user.is_verified:
        code = generate_code()
        user.verification_code = code
        user.verification_expires_at = now_utc() + timedelta(minutes=10)
        db.commit()
        send_required_email(
            user.email,
            "تفعيل البريد الإلكتروني - أكاديمية الرواد",
            verification_email(code),
        )
    return {"message": "إذا كان البريد مسجلاً، فسيتم إرسال رمز جديد"}
