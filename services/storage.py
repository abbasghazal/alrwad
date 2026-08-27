import os
import shutil
import uuid
from typing import BinaryIO, Optional

from fastapi import HTTPException

from app_settings import get_settings
from utils import upload_subdir_path, upload_url


class StoredFile:
    def __init__(self, url: str, key: str, backend: str) -> None:
        self.url = url
        self.key = key
        self.backend = backend


class StorageService:
    """Small storage boundary. Local storage works now; cloud backends plug in here."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def backend(self) -> str:
        return self.settings.storage_backend

    def save(self, stream: BinaryIO, subdir: str, extension: str, filename: Optional[str] = None) -> StoredFile:
        filename = filename or f"{uuid.uuid4()}{extension}"
        if self.backend != "local":
            raise HTTPException(
                status_code=503,
                detail="مزود التخزين السحابي غير مفعّل بعد. استخدم STORAGE_BACKEND=local أو اربط المزود داخل services/storage.py",
            )
        folder = upload_subdir_path(subdir)
        path = os.path.join(folder, filename)
        with open(path, "wb") as buffer:
            shutil.copyfileobj(stream, buffer)
        return StoredFile(url=upload_url(subdir, filename), key=f"{subdir.strip('/')}/{filename}", backend="local")

    def public_url(self, key: str) -> str:
        if self.backend == "local":
            subdir, filename = key.split("/", 1)
            return upload_url(subdir, filename)
        if self.settings.storage_public_base_url:
            return f"{self.settings.storage_public_base_url.rstrip('/')}/{key.lstrip('/')}"
        raise HTTPException(status_code=503, detail="لا يوجد رابط عام مضبوط للتخزين السحابي")
