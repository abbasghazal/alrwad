from typing import Optional

from sqlalchemy.orm import Session

import models


def write_audit_log(
    db: Session,
    action: str,
    actor_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    db.add(
        models.AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
    )
