"""
RoomIQ Dataset & Global Actions API Router.

Endpoints:
- POST /api/dataset/upload: Ingest custom CSV/JSON dataset file.
- POST /api/dataset/preset: Load curated enterprise scenario.
- GET /api/dataset/template: Download sample CSV workplace template.
- POST /api/dataset/reset: Reset to default digital twin.
- GET /api/search: Global quick search for rooms, teams, desks, and bookings.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.database import models as m
from app.database.database import get_db
from app.services.dataset_service import (
    clear_all_workplace_data,
    get_sample_csv_template,
    ingest_dataset_content,
    load_preset_dataset,
)

logger = logging.getLogger("roomiq.api.dataset")
router = APIRouter(prefix="/api", tags=["dataset"])


@router.post("/dataset/upload")
async def upload_dataset_file(
    file: UploadFile = File(...),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        content_bytes = await file.read()
        content_str = content_bytes.decode("utf-8", errors="replace")
        
        result = ingest_dataset_content(db, content_str, filename=file.filename or "dataset.csv")
        return JSONResponse(content=result)
    except Exception as e:
        logger.exception("Dataset upload error: %s", e)
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Failed to ingest dataset: {str(e)}"},
        )


@router.post("/dataset/preset")
async def load_preset(
    request: Request,
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        preset_id = data.get("preset_id") or "digital_twin"
    except Exception:
        preset_id = "digital_twin"

    try:
        result = load_preset_dataset(db, preset_id)
        return JSONResponse(content=result)
    except Exception as e:
        logger.exception("Preset load error: %s", e)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to load preset: {str(e)}"},
        )


@router.get("/dataset/template")
def download_template():
    csv_content = get_sample_csv_template()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=roomiq_dataset_template.csv"},
    )


@router.post("/dataset/reset")
def reset_dataset(
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    result = load_preset_dataset(db, "digital_twin")
    return JSONResponse(content=result)


@router.post("/dataset/clear")
def clear_dataset(
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    result = clear_all_workplace_data(db)
    return JSONResponse(content=result)


@router.get("/search")
def global_search(
    q: str = "",
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not q or len(q.strip()) < 1:
        return JSONResponse(content={"results": []})

    term = f"%{q.strip()}%"
    results = []

    # 1. Search Rooms
    rooms = db.query(m.Room).filter(m.Room.room_name.ilike(term)).limit(5).all()
    for r in rooms:
        results.append({
            "category": "Rooms & Spaces",
            "title": r.room_name,
            "subtitle": f"{r.floor_label} • {r.team_name} • Cap {r.capacity} ({r.chair_inventory} chairs)",
            "url": f"/rooms",
            "icon": "🚪"
        })

    # 2. Search Users / Teams
    users = db.query(m.User).filter(
        (m.User.full_name.ilike(term)) | (m.User.team.ilike(term)) | (m.User.email.ilike(term))
    ).limit(5).all()
    for u in users:
        results.append({
            "category": "People & Teams",
            "title": u.full_name,
            "subtitle": f"{u.team} ({u.department}) • Floor {u.floor_preference} • {u.email}",
            "url": f"/teams",
            "icon": "👥"
        })

    # 3. Search Bookings
    bookings = db.query(m.Booking).filter(m.Booking.title.ilike(term)).limit(4).all()
    for b in bookings:
        room_txt = b.room.room_name if b.room else "Shared Desk"
        results.append({
            "category": "Bookings",
            "title": b.title,
            "subtitle": f"{room_txt} • {b.start_time.strftime('%b %d, %H:%M')} • {b.status.value}",
            "url": f"/bookings",
            "icon": "📅"
        })

    # 4. Search Desks
    desks = db.query(m.Desk).filter(m.Desk.desk_code.ilike(term)).limit(4).all()
    for d in desks:
        results.append({
            "category": "Desks & Chairs",
            "title": f"Desk {d.desk_code}",
            "subtitle": f"Floor {d.floor} • {d.zone} • {d.status}",
            "url": f"/desks",
            "icon": "🪑"
        })

    return JSONResponse(content={"results": results})
