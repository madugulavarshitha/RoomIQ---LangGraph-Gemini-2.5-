from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.ai.gemini_service import extract_meeting_requirements
from app.database import models as m
from app.database import repositories as repo
from app.database.database import get_db
from app.services import tools
from app.services.booking_service import cancel_booking, create_booking
from app.services.notification_service import unread_count
from app.templating import templates

router = APIRouter()


@router.get("/bookings")
def bookings_page(
    request: Request,
    date: str | None = Query(None),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    today = dt.date.today()
    if date:
        try:
            selected_date = dt.datetime.strptime(date, "%Y-%m-%d").date()
        except Exception:
            selected_date = today
    else:
        selected_date = today

    all_rooms = repo.list_rooms(db)
    all_users = db.query(m.User).order_by(m.User.team, m.User.full_name).all()

    # Query active bookings for selected date
    day_start = dt.datetime.combine(selected_date, dt.time.min)
    day_end = dt.datetime.combine(selected_date, dt.time.max)
    day_bookings_query = db.query(m.Booking).filter(
        m.Booking.start_time >= day_start,
        m.Booking.start_time <= day_end,
        m.Booking.status != m.BookingStatus.CANCELLED,
    ).order_by(m.Booking.start_time).all()

    room_lookup = {r.id: r for r in all_rooms}
    user_lookup = {u.id: u for u in all_users}

    calendar_bookings = []
    for b in day_bookings_query:
        r = room_lookup.get(b.room_id)
        u = user_lookup.get(b.user_id)
        attendee_list = [a.strip() for a in (b.attendee_names or "").split(",") if a.strip()]
        if not attendee_list and u:
            attendee_list = [u.full_name]

        chairs_allocated = b.allocated_chairs if b.allocated_chairs is not None else min(b.expected_attendees, r.chair_inventory if r else b.expected_attendees)
        chair_inv = r.chair_inventory if r else 0
        buffer_val = chair_inv - chairs_allocated

        # Determine theme color for booking chip
        title_lower = b.title.lower()
        if "sync" in title_lower or "strategy" in title_lower:
            theme_color = "purple"
        elif "review" in title_lower or "design" in title_lower:
            theme_color = "mint"
        elif "1:1" in title_lower or "one" in title_lower or "client" in title_lower:
            theme_color = "blue"
        elif "hiring" in title_lower or "interview" in title_lower:
            theme_color = "peach"
        elif "all hands" in title_lower or "workshop" in title_lower:
            theme_color = "pink"
        else:
            theme_color = "purple"

        calendar_bookings.append({
            "id": b.id,
            "title": b.title,
            "meeting_type": b.meeting_type or "General Meeting",
            "room_id": b.room_id,
            "room_name": r.room_name if r else "Shared Space",
            "room_short_name": r.room_name.split("—")[-1].strip() if r else "Room",
            "floor": r.floor if r else 0,
            "floor_label": r.floor_label if r else "Ground Floor",
            "room_type": r.room_type if r else "Meeting Space",
            "capacity": r.capacity if r else 4,
            "chair_inventory": chair_inv,
            "allocated_chairs": chairs_allocated,
            "chair_buffer": buffer_val,
            "start_time_iso": b.start_time.isoformat(),
            "end_time_iso": b.end_time.isoformat(),
            "start_str": b.start_time.strftime("%H:%M"),
            "end_str": b.end_time.strftime("%H:%M"),
            "start_hour": b.start_time.hour + (b.start_time.minute / 60.0),
            "duration_hours": (b.end_time - b.start_time).total_seconds() / 3600.0,
            "expected_attendees": b.expected_attendees,
            "attendees": attendee_list,
            "attendee_count": max(len(attendee_list), b.expected_attendees),
            "organizer_name": u.full_name if u else "Colleague",
            "organizer_team": u.team if u else "General",
            "status": b.status.value,
            "theme_color": theme_color,
            "requires_projector": b.requires_projector,
            "requires_video": b.requires_video,
        })

    # Group rooms / cabins by floor for cabin booking selector
    cabins_by_floor = {
        "Ground Floor": [r for r in all_rooms if r.floor == 0],
        "3rd Floor": [r for r in all_rooms if r.floor == 3],
        "6th Floor": [r for r in all_rooms if r.floor == 6],
    }

    # Summary metrics matching header in reference
    total_day_meetings = len(calendar_bookings)
    total_allocated_chairs = sum(cb["allocated_chairs"] for cb in calendar_bookings)
    booked_room_ids = {cb["room_id"] for cb in calendar_bookings}
    available_cabins_count = len([r for r in all_rooms if "Cabin" in r.room_type and r.id not in booked_room_ids]) or 22
    summary = {
        "total_meetings": total_day_meetings,
        "total_chairs_allocated": total_allocated_chairs,
        "available_cabins": available_cabins_count,
        "total_floors": 3,
        "total_spaces": len(all_rooms) or 30,
    }

    my_bookings = sorted(user.bookings, key=lambda b: b.start_time, reverse=True)[:20]

    # Serialized colleagues list for autocomplete attendee picker
    colleagues_json = [
        {
            "id": u.id,
            "name": u.full_name,
            "email": u.email,
            "team": u.team,
            "department": u.department,
            "work_mode": u.work_mode,
            "floor_pref": u.floor_preference,
        }
        for u in all_users
    ]

    # Serialized rooms list for dynamic calendar rendering
    rooms_json = [
        {
            "id": r.id,
            "name": r.room_name,
            "short_name": r.room_name.split("—")[-1].strip(),
            "floor": r.floor,
            "floor_label": r.floor_label,
            "team_name": r.team_name,
            "room_type": r.room_type,
            "capacity": r.capacity,
            "min_capacity": r.min_capacity,
            "max_capacity": r.max_capacity,
            "chairs": r.chair_inventory,
            "benches": r.bench_count or 0,
            "is_executive": r.is_executive,
            "projector": r.projector_available,
            "video": r.video_conferencing,
            "whiteboard": r.whiteboard,
        }
        for r in all_rooms
    ]

    return templates.TemplateResponse(
        "bookings.html",
        {
            "request": request,
            "user": user,
            "selected_date": selected_date.strftime("%Y-%m-%d"),
            "selected_date_display": selected_date.strftime("%A, %B %d, %Y"),
            "is_today": selected_date == today,
            "prev_date": (selected_date - dt.timedelta(days=1)).strftime("%Y-%m-%d"),
            "next_date": (selected_date + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
            "calendar_bookings": calendar_bookings,
            "calendar_bookings_json": json.dumps(calendar_bookings),
            "rooms": all_rooms,
            "rooms_json": json.dumps(rooms_json),
            "colleagues": all_users,
            "colleagues_json": json.dumps(colleagues_json),
            "cabins_by_floor": cabins_by_floor,
            "my_bookings": my_bookings,
            "summary": {
                "total_meetings": total_day_meetings,
                "total_chairs_allocated": total_allocated_chairs,
                "available_cabins": available_cabins_count,
                "total_spaces": len(all_rooms),
            },
            "unread": unread_count(db, user.id),
            "match": None,
            "requirements": None,
            "form": None,
        },
    )


@router.post("/bookings/smart-match")
def smart_match(
    request: Request,
    description: str = Form(...),
    date: str = Form(...),
    start_time: str = Form(...),
    duration_minutes: int = Form(60),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    requirements = extract_meeting_requirements(description)
    day = dt.datetime.strptime(date, "%Y-%m-%d").date()
    start_dt = dt.datetime.combine(day, dt.datetime.strptime(start_time, "%H:%M").time())
    end_dt = start_dt + dt.timedelta(minutes=duration_minutes)

    result = tools.find_available_rooms(
        db,
        day=day,
        start=start_dt,
        end=end_dt,
        min_capacity=requirements["participants"],
        require_projector=requirements["requires_projector"],
        require_video=requirements["requires_video"],
        preferred_floor=requirements.get("preferred_floor"),
        preferred_zone=requirements.get("preferred_zone"),
    )

    all_rooms = repo.list_rooms(db)
    all_users = db.query(m.User).order_by(m.User.team, m.User.full_name).all()
    my_bookings = sorted(user.bookings, key=lambda b: b.start_time, reverse=True)[:20]

    # Calculate chair compatibility for matched rooms
    enhanced_matches = []
    for cand in result.get("candidates", []):
        r_id = cand.get("room_id")
        r_obj = db.get(m.Room, r_id)
        chair_inv = r_obj.chair_inventory if r_obj else cand.get("capacity", 0)
        req_participants = requirements.get("participants", 1)
        chair_fit = "Perfect Fit" if chair_inv >= req_participants else f"Needs {req_participants - chair_inv} more chairs"

        enhanced_matches.append({
            **cand,
            "chair_inventory": chair_inv,
            "chair_fit": chair_fit,
            "is_cabin": "Cabin" in (r_obj.room_type if r_obj else ""),
            "floor_label": r_obj.floor_label if r_obj else f"Floor {cand.get('floor')}",
            "room_type": r_obj.room_type if r_obj else "Meeting Space",
        })

    # Return standard bookings page response with match data
    return templates.TemplateResponse(
        "bookings.html",
        {
            "request": request,
            "user": user,
            "selected_date": date,
            "selected_date_display": day.strftime("%A, %B %d, %Y"),
            "is_today": day == dt.date.today(),
            "prev_date": (day - dt.timedelta(days=1)).strftime("%Y-%m-%d"),
            "next_date": (day + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
            "calendar_bookings": [],
            "calendar_bookings_json": json.dumps([]),
            "rooms": all_rooms,
            "rooms_json": json.dumps([{"id": r.id, "name": r.room_name, "chairs": r.chair_inventory, "capacity": r.capacity} for r in all_rooms]),
            "colleagues": all_users,
            "colleagues_json": json.dumps([{"id": u.id, "name": u.full_name, "team": u.team} for u in all_users]),
            "cabins_by_floor": {
                "Ground Floor": [r for r in all_rooms if r.floor == 0],
                "3rd Floor": [r for r in all_rooms if r.floor == 3],
                "6th Floor": [r for r in all_rooms if r.floor == 6],
            },
            "my_bookings": my_bookings,
            "summary": {"total_meetings": 0, "total_chairs_allocated": 0, "available_cabins": 12, "total_spaces": len(all_rooms)},
            "unread": unread_count(db, user.id),
            "match": enhanced_matches,
            "requirements": requirements,
            "form": {"description": description, "date": date, "start_time": start_time, "duration_minutes": duration_minutes},
        },
    )


@router.post("/bookings/create")
def create_booking_route(
    request: Request,
    room_id: str = Form(...),
    title: str = Form(...),
    meeting_type: str = Form("General Meeting"),
    date: str = Form(...),
    start_time: str = Form(...),
    duration_minutes: int = Form(60),
    participants: int = Form(1),
    allocated_chairs: int | None = Form(None),
    attendee_names: str = Form(""),
    requires_projector: bool = Form(False),
    requires_video: bool = Form(False),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    day = dt.datetime.strptime(date, "%Y-%m-%d").date()
    start_dt = dt.datetime.combine(day, dt.datetime.strptime(start_time, "%H:%M").time())
    end_dt = start_dt + dt.timedelta(minutes=duration_minutes)

    result = create_booking(
        db,
        user_id=user.id,
        room_id=room_id,
        title=title,
        meeting_type=meeting_type,
        start_time=start_dt,
        end_time=end_dt,
        expected_attendees=participants,
        allocated_chairs=allocated_chairs if allocated_chairs is not None else participants,
        attendee_names=attendee_names,
        requires_projector=requires_projector,
        requires_video=requires_video,
    )
    return RedirectResponse(f"/bookings?date={date}", status_code=303)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking_route(
    booking_id: str,
    date: str | None = Form(None),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cancel_booking(db, booking_id, reason=f"Cancelled by {user.full_name} via Bookings Hub")
    target_url = f"/bookings?date={date}" if date else "/bookings"
    return RedirectResponse(target_url, status_code=303)


@router.get("/api/bookings")
def api_bookings(db: Session = Depends(get_db)):
    return JSONResponse(tools.get_bookings(db))


@router.get("/api/bookings/date/{date_str}")
def api_bookings_by_date(date_str: str, db: Session = Depends(get_db)):
    try:
        target_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        target_date = dt.date.today()

    day_start = dt.datetime.combine(target_date, dt.time.min)
    day_end = dt.datetime.combine(target_date, dt.time.max)
    bookings = db.query(m.Booking).filter(
        m.Booking.start_time >= day_start,
        m.Booking.start_time <= day_end,
        m.Booking.status != m.BookingStatus.CANCELLED,
    ).all()

    rooms = {r.id: r for r in repo.list_rooms(db)}
    users = {u.id: u for u in db.query(m.User).all()}

    results = []
    for b in bookings:
        r = rooms.get(b.room_id)
        u = users.get(b.user_id)
        results.append({
            "id": b.id,
            "title": b.title,
            "meeting_type": b.meeting_type or "Meeting",
            "room_id": b.room_id,
            "room_name": r.room_name if r else "Room",
            "floor": r.floor if r else 0,
            "floor_label": r.floor_label if r else "Floor",
            "capacity": r.capacity if r else 4,
            "chair_inventory": r.chair_inventory if r else 0,
            "allocated_chairs": b.allocated_chairs or b.expected_attendees,
            "expected_attendees": b.expected_attendees,
            "attendees": [a.strip() for a in (b.attendee_names or "").split(",") if a.strip()],
            "organizer": u.full_name if u else "Colleague",
            "start": b.start_time.strftime("%H:%M"),
            "end": b.end_time.strftime("%H:%M"),
            "status": b.status.value,
        })
    return JSONResponse({"date": date_str, "count": len(results), "bookings": results})

