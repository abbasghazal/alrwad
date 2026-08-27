import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Query as SQLAlchemyQuery
from app_settings import get_settings


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="رقم الصفحة"),
        per_page: int = Query(10, ge=1, le=100, description="عدد العناصر في الصفحة"),
    ):
        self.page = page
        self.per_page = per_page


class PaginatedResponse(BaseModel):
    items: List[Any]
    page: int
    per_page: int
    total: int
    total_pages: int


def paginate_query(query: SQLAlchemyQuery, params: PaginationParams) -> Dict[str, Any]:
    total = query.count()
    total_pages = max(1, math.ceil(total / params.per_page))
    items = query.offset((params.page - 1) * params.per_page).limit(params.per_page).all()
    return {
        "items": [serialize_item(item) for item in items],
        "page": params.page,
        "per_page": params.per_page,
        "total": total,
        "total_pages": total_pages,
    }


def serialize_item(item: Any) -> Any:
    if hasattr(item, "__table__"):
        hidden = {
            "password_hash",
            "verification_code",
            "refresh_token_hash",
            "permissions",
        }
        return jsonable_encoder({
            column.name: getattr(item, column.name)
            for column in item.__table__.columns
            if column.name not in hidden
        })
    return jsonable_encoder(item)


def safe_delete_static_file(url: Optional[str], allowed_fragment: str) -> None:
    if not url:
        return
    path = uploaded_url_to_path(url)
    if not path:
        path = url.replace("/static/", "static/", 1)
    if allowed_fragment not in path.replace("\\", "/") or not os.path.exists(path):
        return
    try:
        os.remove(path)
    except OSError:
        pass


def upload_subdir_path(subdir: str) -> str:
    settings = get_settings()
    path = os.path.join(settings.upload_root, subdir)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        fallback_root = "/tmp/alrwad_uploads"
        print(f"[STORAGE] Cannot use UPLOAD_ROOT={settings.upload_root}: {exc}. Falling back to {fallback_root}.")
        settings.upload_root = fallback_root
        path = os.path.join(settings.upload_root, subdir)
        os.makedirs(path, exist_ok=True)
    return path


def upload_url(subdir: str, filename: str) -> str:
    settings = get_settings()
    return f"{settings.upload_url_prefix}/{subdir.strip('/')}/{filename}"


def uploaded_url_to_path(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    settings = get_settings()
    prefix = settings.upload_url_prefix + "/"
    if url.startswith(prefix):
        relative = url[len(prefix):]
        return os.path.join(settings.upload_root, relative)
    if url.startswith("/static/uploads/"):
        return url.replace("/static/uploads/", "static/uploads/", 1)
    return None
