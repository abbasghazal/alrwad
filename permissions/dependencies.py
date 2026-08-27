from fastapi import Depends, HTTPException, status
from typing import Set

import auth
import models


ROLE_PERMISSIONS = {
    "owner": {
        "can_edit_subject",
        "can_delete_lecture",
        "can_manage_users",
        "can_grade_students",
        "can_manage_tutors",
    },
    "teacher": {"can_delete_lecture", "can_grade_students"},
    "tutor": {"can_manage_tutors"},
    "student": set(),
}


def user_permissions(user: models.User) -> Set[str]:
    explicit = {p.strip() for p in (user.permissions or "").split(",") if p.strip()}
    return ROLE_PERMISSIONS.get(user.role, set()) | explicit


def require(permission: str):
    def dependency(current_user: models.User = Depends(auth.get_current_user)) -> models.User:
        if permission not in user_permissions(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="لا تملك الصلاحية المطلوبة")
        return current_user

    return dependency
