import hashlib
import secrets
from datetime import timedelta
from typing import Optional, Tuple
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from database import get_db
from app_settings import get_settings
import models
from utils import ensure_aware_utc, now_utc

# إعداد مفاتيح التشفير والـ JWT
SECRET_KEY = get_settings().jwt_secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

# محدد موقع التوكين من الطلبات
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """التحقق من تطابق كلمة المرور المدخلة مع المشفرة"""
    try:
        password_bytes = plain_password.encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except (TypeError, ValueError, bcrypt.errors.BcryptError):
        return False

def get_password_hash(password: str) -> str:
    """تشفير كلمة المرور"""
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """توليد رمز مصادقة JWT جديد"""
    to_encode = data.copy()
    if expires_delta:
        expire = now_utc() + expires_delta
    else:
        expire = now_utc() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access", "jti": secrets.token_urlsafe(16)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: models.User, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> Tuple[str, int]:
    refresh_token = create_refresh_token()
    session = models.UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        ip_address=ip_address,
        browser=user_agent[:255] if user_agent else None,
        device_name=user_agent[:255] if user_agent else None,
        expires_at=now_utc() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        last_activity=now_utc(),
    )
    db.add(session)
    db.flush()
    return refresh_token, session.id

def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """التأكد من هوية المستخدم بناء على رمز JWT المرفق"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="تعذر التحقق من بيانات الجلسة. يرجى تسجيل الدخول مجدداً",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exception
        username: str = payload.get("sub")
        session_id = payload.get("sid")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception

    if session_id:
        session = db.query(models.UserSession).filter(
            models.UserSession.id == session_id,
            models.UserSession.user_id == user.id,
        ).first()
        if not session or session.is_revoked or ensure_aware_utc(session.expires_at) < now_utc():
            raise credentials_exception
        
    if user.is_blocked or getattr(user, "is_deleted", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="تم حظر حسابك من قبل الإدارة"
        )
    if not user.is_verified and user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="يجب تفعيل البريد الإلكتروني قبل استخدام الحساب"
        )
        
    return user

def get_current_student(current_user: models.User = Depends(get_current_user)) -> models.User:
    """التأكد من أن المستخدم الحالي طالب"""
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذا الإجراء متاح للطلاب فقط"
        )
    return current_user

def get_current_teacher(current_user: models.User = Depends(get_current_user)) -> models.User:
    """التأكد من أن المستخدم الحالي مدرس أو مدرس خصوصي"""
    if current_user.role not in ["teacher", "tutor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذا الإجراء متاح للمدرسين فقط"
        )
    return current_user

def get_current_owner(current_user: models.User = Depends(get_current_user)) -> models.User:
    """التأكد من أن المستخدم الحالي مالك المنصة (مدير)"""
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذا الإجراء متاح لمدير المنصة فقط"
        )
    return current_user


def require_permission(permission: str):
    def dependency(current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role == "owner":
            return current_user
        permissions = getattr(current_user, "permissions", "") or ""
        if permission not in {p.strip() for p in permissions.split(",") if p.strip()}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="لا تملك الصلاحية المطلوبة")
        return current_user

    return dependency
