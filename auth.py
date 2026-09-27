from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_user
from app.auth.security import SESSION_COOKIE, create_session_token, hash_password, verify_password
from app.database import models as m
from app.database.database import get_db
from app.database import repositories as repo
from app.templating import templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(m.User).filter(m.User.email == email.strip().lower()).first()
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password."}, status_code=401)

    token = create_session_token(user.id)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 8)
    return resp


@router.get("/signup")
def signup_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@router.post("/signup")
def signup_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    department: str = Form("Operations"),
    role: str = Form("ADMIN"),
    team: str = Form("Operations Team"),
    work_mode: str = Form("In-Office"),
    floor_preference: int = Form(0),
    db: Session = Depends(get_db),
):
    email_norm = email.strip().lower()
    if db.query(m.User).filter(m.User.email == email_norm).first():
        return templates.TemplateResponse("signup.html", {"request": request, "error": "An account with that email already exists."}, status_code=400)
    if len(password) < 6:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Password must be at least 6 characters."}, status_code=400)

    try:
        user_role = m.Role(role.upper())
    except Exception:
        user_role = m.Role.EMPLOYEE

    user = m.User(
        full_name=full_name.strip(),
        email=email_norm,
        password_hash=hash_password(password),
        role=user_role,
        department=department or "Operations",
        team=team or "Operations Team",
        work_mode=work_mode or "In-Office",
        floor_preference=floor_preference,
    )
    db.add(user)
    db.commit()

    token = create_session_token(user.id)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 8)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/profile")
def profile(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    my_bookings = [b for b in user.bookings][-10:]
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": user, "bookings": my_bookings},
    )
