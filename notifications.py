from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.database import models as m
from app.database.database import get_db
from app.services.notification_service import list_notifications, mark_read, unread_count
from app.templating import templates

router = APIRouter()


@router.get("/notifications")
def notifications_page(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    notes = list_notifications(db, user.id)
    return templates.TemplateResponse(
        "notifications.html",
        {"request": request, "user": user, "notifications": notes, "unread": unread_count(db, user.id)},
    )


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    mark_read(db, notification_id)
    return RedirectResponse("/notifications", status_code=303)


@router.get("/api/notifications")
def api_notifications(user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    notes = list_notifications(db, user.id)
    return JSONResponse(
        {
            "unread": unread_count(db, user.id),
            "notifications": [
                {"id": n.id, "category": n.category, "title": n.title, "message": n.message, "read": n.read, "created_at": n.created_at.isoformat()}
                for n in notes
            ],
        }
    )
