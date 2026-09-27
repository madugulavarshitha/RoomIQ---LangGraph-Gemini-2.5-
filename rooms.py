from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.database import models as m
from app.database import repositories as repo
from app.database.database import get_db
from app.services.notification_service import unread_count
from app.services.occupancy_service import calculate_room_utilization, classify_room
from app.services import tools
from app.templating import templates

router = APIRouter()


@router.get("/rooms")
def room_directory(
    request: Request,
    floor: str | None = None,
    team: str | None = None,
    min_capacity: int | None = None,
    equipment: str | None = None,
    selected_id: str | None = None,
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    all_rooms = repo.list_rooms(db)
    
    # Filter rooms if parameters supplied
    filtered_rooms = list(all_rooms)
    if floor and floor.lower() != "all":
        try:
            fl_int = int(floor)
            filtered_rooms = [r for r in filtered_rooms if r.floor == fl_int]
        except ValueError:
            pass

    if team and team.lower() != "all":
        filtered_rooms = [r for r in filtered_rooms if team.lower() in (r.team_name or "").lower()]

    if min_capacity:
        filtered_rooms = [r for r in filtered_rooms if r.capacity >= min_capacity]

    # Map team badge style classes
    team_badge_map = {
        "product": "product",
        "operations": "operations",
        "fsd": "fsd",
        "servicenow": "servicenow",
        "salesforce": "salesforce",
        "ai": "aitech",
        "tech": "aitech",
        "marketing": "marketing",
    }

    # Available room thumbnails pool
    thumbs = [
        "/static/img/space_card_gf_c1.jpg",
        "/static/img/space_card_gf_c2.jpg",
        "/static/img/space_card_gf_hall.jpg",
        "/static/img/space_card_3f_c1.jpg",
        "/static/img/space_card_fsd.jpg",
        "/static/img/space_card_salesforce.jpg",
    ]

    space_cards = []
    available_count = 0
    occupied_count = 0

    for idx, r in enumerate(filtered_rooms):
        t_lower = (r.team_name or "general").lower()
        t_badge = "product"
        for k, v in team_badge_map.items():
            if k in t_lower:
                t_badge = v
                break

        # Calculate estimated occupancy & status
        occ_rec = db.query(m.OccupancyRecord).filter(m.OccupancyRecord.room_id == r.id).order_by(m.OccupancyRecord.timestamp.desc()).first()
        occ_num = occ_rec.detected_occupants if occ_rec else min(r.capacity, max(1, round(r.capacity * 0.7)))
        
        util_pct = min(100, round((occ_num / max(1, r.capacity)) * 100))
        
        if r.chair_inventory < r.capacity:
            status = "Seating Pressure"
            status_badge = "warning"
            pressure_tag = "CHAIR GAP"
            insight = f"Capacity is {r.capacity} but only {r.chair_inventory} chairs are tracked. Additional seating may be needed."
            occupied_count += 1
        elif util_pct >= 85:
            status = "Occupied"
            status_badge = "occupied"
            pressure_tag = "HIGH DEMAND"
            insight = f"High continuous occupancy ({occ_num}/{r.capacity} seats used)."
            occupied_count += 1
        elif util_pct < 40:
            status = "Underutilized"
            status_badge = "underutilized"
            pressure_tag = "AVAILABLE CAPACITY"
            insight = "Capacity available for ad-hoc collaboration sessions."
            available_count += 1
        else:
            status = "Available"
            status_badge = "available"
            pressure_tag = "OPTIMIZED"
            insight = "Optimal utilization. Good balance of occupancy and capacity."
            available_count += 1

        img_thumb = thumbs[idx % len(thumbs)]
        space_cards.append({
            "id": r.id,
            "name": r.room_name,
            "floor": r.floor_label or (f"Floor {r.floor}" if r.floor > 0 else "Ground Floor"),
            "type": r.room_type or ("Cabin" if r.capacity <= 8 else "Major Hall"),
            "team": r.team_name or "Shared Space",
            "team_badge": t_badge,
            "status": status,
            "status_badge": status_badge,
            "capacity": f"{max(1, r.capacity // 2)} – {r.capacity}",
            "chairs": r.chair_inventory,
            "occupancy": f"{occ_num} / {r.capacity}",
            "utilization": f"{util_pct}%",
            "current_occ_num": occ_num,
            "thumb": img_thumb,
            "hero_img": img_thumb,
            "insight": insight,
            "pressure_tag": pressure_tag,
        })

    total_spaces_count = len(all_rooms)
    if total_spaces_count > 0:
        availability_pct = f"{round((available_count / max(1, len(space_cards) or 1)) * 100)}%"
    else:
        availability_pct = "100%"

    # Selected space for right sidebar detail panel
    selected_space = None
    if selected_id:
        selected_space = next((s for s in space_cards if str(s["id"]) == selected_id), None)
    if not selected_space and space_cards:
        # Default to first card with high demand/seating pressure or first card
        selected_space = next((s for s in space_cards if "PRESSURE" in s["pressure_tag"] or "GAP" in s["pressure_tag"]), space_cards[0])

    return templates.TemplateResponse(
        "rooms.html",
        {
            "request": request,
            "user": user,
            "total_spaces_count": total_spaces_count,
            "available_spaces_count": available_count,
            "occupied_spaces_count": occupied_count,
            "availability_pct": availability_pct,
            "space_cards": space_cards,
            "selected_space": selected_space,
            "unread": unread_count(db, user.id) if user else 4,
        },
    )


@router.get("/api/rooms")
def api_rooms(db: Session = Depends(get_db)):
    return JSONResponse(tools.get_room_inventory(db))


@router.get("/api/rooms/{room_id}")
def api_room_detail(room_id: str, db: Session = Depends(get_db)):
    room = repo.get_room(db, room_id)
    if room is None:
        return JSONResponse({"error": "Room not found"}, status_code=404)
    status = classify_room(db, room, dt.datetime.utcnow())
    return JSONResponse({
        "room_id": room.id,
        "room_name": room.room_name,
        "floor": room.floor,
        "team_name": room.team_name,
        "capacity": room.capacity,
        "chair_inventory": room.chair_inventory,
        "status": status["status"],
    })
