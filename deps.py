from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.security import SESSION_COOKIE, read_session_token
from app.database import models as m
from app.database.database import get_db


def get_current_user(request: Request, db: Session = Depends(get_db)) -> m.User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    user_id = read_session_token(token)
    if not user_id or not isinstance(user_id, str):
        return None
    try:
        return db.get(m.User, user_id)
    except Exception:
        return None


def require_user(request: Request, db: Session = Depends(get_db)) -> m.User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_role(*roles: m.Role):
    def _dep(user: m.User = Depends(require_user)) -> m.User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions for this area.")
        return user

    return _dep


require_manager_or_admin = require_role(m.Role.FACILITIES_MANAGER, m.Role.ADMIN)
require_admin = require_role(m.Role.ADMIN)
