import sys
from pathlib import Path
import time
from contextlib import contextmanager

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app_settings import get_settings


SQLALCHEMY_DATABASE_URL = get_settings().database_url

# إنشاء محرك قاعدة البيانات
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

# إنشاء مصنع جلسات قاعدة البيانات
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# الفئة الأساسية للنماذج
Base = declarative_base()

# دالة للحصول على جلسة قاعدة البيانات كـ Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database(max_attempts: int = 3, delay_seconds: float = 1.0) -> bool:
    last_error = None
    for _ in range(max_attempts):
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return True
        except Exception as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(f"Database connection failed: {last_error}")
