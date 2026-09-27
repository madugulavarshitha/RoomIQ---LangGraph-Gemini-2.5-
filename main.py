from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, auth, bookings, dashboard, dataset, desks, notifications, optimization, reports, rooms, teams
from app.config import settings
from app.database.database import init_db, session_scope
from app.services.simulation_service import seed_all
from app.templating import templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("roomiq")

app = FastAPI(title="RoomIQ", description="Multi-Agent Workplace Utilization & Reallocation System")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


from app.database import models as m

@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with session_scope() as db:
        if settings.RESEED:
            seed_all(db, force=True)
        else:
            admin = db.query(m.User).filter(m.User.email == "admin@roomiq.io").first()
            if not admin:
                from app.auth.security import hash_password
                admin = m.User(
                    full_name="Ava Sharma",
                    email="admin@roomiq.io",
                    password_hash=hash_password("Admin123!"),
                    role=m.Role.ADMIN,
                    department="Operations",
                    team="Operations Team",
                    work_mode="In-Office",
                    floor_preference=0,
                )
                db.add(admin)
                db.commit()
    logger.info("RoomIQ startup complete. Gemini enabled: %s", settings.gemini_enabled)


@app.exception_handler(303)
@app.exception_handler(307)
async def redirect_handler(request: Request, exc):
    location = exc.headers.get("Location", "/login") if hasattr(exc, "headers") and exc.headers else "/login"
    return RedirectResponse(url=location, status_code=303)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return templates.TemplateResponse("error.html", {"request": request, "code": 404, "message": "That page doesn't exist."}, status_code=404)


@app.exception_handler(403)
async def forbidden(request: Request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return templates.TemplateResponse("error.html", {"request": request, "code": 403, "message": "You don't have access to this area."}, status_code=403)


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(rooms.router)
app.include_router(desks.router)
app.include_router(bookings.router)
app.include_router(reports.router)
app.include_router(optimization.router)
app.include_router(analytics.router)
app.include_router(notifications.router)
app.include_router(teams.router)
app.include_router(dataset.router)
