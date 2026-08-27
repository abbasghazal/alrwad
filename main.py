import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import inspect

from background_jobs.scheduler import Scheduler
from app_settings import get_settings
from database import check_database, engine, SessionLocal
from email_service import EmailService
from middleware.csrf import CSRFMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from utils import uploaded_url_to_path
import models
import auth

# استيراد المسارات
from routes import auth as auth_routes
from routes import subjects as subject_routes
from routes import lectures as lecture_routes
from routes import homeworks as homework_routes
from routes import ratings as rating_routes
from routes import users as user_routes
from routes import admin as admin_routes
from routes import tutors as tutor_routes
from routes import payments as payment_routes
from routes import learning as learning_routes

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
    from slowapi import _rate_limit_exceeded_handler
except ImportError:
    Limiter = None
    RateLimitExceeded = None
    SlowAPIMiddleware = None
    get_remote_address = None
    _rate_limit_exceeded_handler = None

settings = get_settings()
scheduler = Scheduler()


def ensure_required_tables():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = set(models.Base.metadata.tables.keys())
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        raise RuntimeError(
            "Database schema is not migrated. Missing tables: " + ", ".join(missing_tables)
        )


def ensure_upload_directories():
    from utils import upload_subdir_path

    upload_subdir_path("avatars")
    upload_subdir_path("homeworks")


def ensure_email_service():
    email_service = EmailService()
    if not email_service.is_configured:
        missing = ", ".join(email_service.config_errors) or "Email API settings"
        print(f"[SETUP] Email API is not configured: {missing}. Email-dependent actions will continue without delivery.")
        return
    delivery_method = "Email API" if email_service.settings.email_api_configured else "SMTP"
    print(f"[SETUP] Email delivery is configured via {delivery_method}.")


def ensure_default_owner():
    db = SessionLocal()
    try:
        owner = db.query(models.User).filter(models.User.role == "owner", models.User.is_deleted == False).first()
        if not owner:
            if not settings.default_owner_password:
                print("[SETUP] DEFAULT_OWNER_PASSWORD is not set. Skipping default owner creation.")
                return

            hashed_pw = auth.get_password_hash(settings.default_owner_password)
            default_owner = models.User(
                first_name="مدير",
                last_name="المنصة",
                username=settings.default_owner_username,
                email=settings.default_owner_email,
                password_hash=hashed_pw,
                role="owner",
                is_verified=True,
            )
            db.add(default_owner)
            db.commit()
            print(f"\n[SETUP] Default owner created: Username: {settings.default_owner_username}\n")
    except Exception as e:
        print(f"Error creating default owner: {e}")
        raise
    finally:
        db.close()


def cleanup_unused_uploads():
    db = SessionLocal()
    try:
        used_files = set()
        used_files.update(
            uploaded_url_to_path(url) or url.replace("/static/", "static/", 1)
            for (url,) in db.query(models.User.avatar_url).filter(models.User.avatar_url.isnot(None)).all()
        )
        used_files.update(
            uploaded_url_to_path(url) or url.replace("/static/", "static/", 1)
            for (url,) in db.query(models.Homework.file_url).filter(models.Homework.file_url.isnot(None)).all()
        )
        used_files.update(
            uploaded_url_to_path(url) or url.replace("/static/", "static/", 1)
            for (url,) in db.query(models.Submission.file_url).filter(models.Submission.file_url.isnot(None)).all()
        )

        for folder in (
            os.path.join(settings.upload_root, "avatars"),
            os.path.join(settings.upload_root, "homeworks"),
        ):
            for filename in os.listdir(folder):
                path = os.path.join(folder, filename)
                if os.path.isfile(path) and path not in used_files:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_database()
    ensure_required_tables()
    ensure_default_owner()
    ensure_email_service()
    ensure_upload_directories()

    scheduler.every(60 * 60 * 24, cleanup_unused_uploads)
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(
    title="أكاديمية الرواد التعليمية API",
    description="الخلفية البرمجية للمنصة التعليمية أكاديمية الرواد",
    version="1.0.0",
    lifespan=lifespan,
)


if Limiter:
    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

# إعداد الـ CORS من متغيرات البيئة مع نطاقات التطوير المحلية فقط
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)

# ربط المسارات بالـ API
app.include_router(auth_routes.router, prefix="/api")
app.include_router(subject_routes.router, prefix="/api")
app.include_router(lecture_routes.router, prefix="/api")
app.include_router(homework_routes.router, prefix="/api")
app.include_router(rating_routes.router, prefix="/api")
app.include_router(user_routes.router, prefix="/api")
app.include_router(admin_routes.router, prefix="/api")
app.include_router(tutor_routes.router, prefix="/api")
app.include_router(payment_routes.router, prefix="/api")
app.include_router(learning_routes.router, prefix="/api")

# ربط الملفات الاستاتيكية للواجهة الأمامية
ensure_upload_directories()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount(settings.upload_url_prefix, StaticFiles(directory=settings.upload_root), name="uploads")

# توجيه الصفحة الرئيسية لملف index.html
@app.get("/")
def read_root():
    return FileResponse("static/index.html")


@app.head("/")
def head_root():
    return None


@app.get("/health")
def health_check():
    database_status = "ok"
    try:
        check_database(max_attempts=1)
    except Exception:
        database_status = "failed"

    storage_status = "ok" if all(
        os.path.isdir(path) and os.access(path, os.W_OK)
        for path in (
            os.path.join(settings.upload_root, "avatars"),
            os.path.join(settings.upload_root, "homeworks"),
        )
    ) else "failed"

    return {
        "database_status": database_status,
        "email_status": "ok" if EmailService().is_configured else "not_configured",
        "storage_status": storage_status,
        "scheduler_status": "ok" if scheduler.ready else "not_ready",
        "server_status": "ok",
    }

# توجيه أي مسار غير معروف للـ SPA
@app.get("/{full_path:path}")
def catch_all(full_path: str):
    # إذا كان المسار يبدأ بـ api أو static نتركه يمر بشكل طبيعي (سيعود بـ 404 إذا لم يكن موجوداً)
    if full_path.startswith("api") or full_path.startswith("static"):
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse("static/index.html")
