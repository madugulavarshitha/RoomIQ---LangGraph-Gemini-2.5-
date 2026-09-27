from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as m


def list_notifications(db: Session, user_id: str | None = None, limit: int = 50) -> list[m.Notification]:
    stmt = select(m.Notification).order_by(m.Notification.created_at.desc()).limit(limit)
    if user_id:
        stmt = select(m.Notification).where(
            (m.Notification.user_id == user_id) | (m.Notification.user_id.is_(None))
        ).order_by(m.Notification.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def unread_count(db: Session, user_id: str | None = None) -> int:
    return len([n for n in list_notifications(db, user_id, limit=200) if not n.read])


def mark_read(db: Session, notification_id: str) -> bool:
    n = db.get(m.Notification, notification_id)
    if n is None:
        return False
    n.read = True
    db.commit()
    return True
