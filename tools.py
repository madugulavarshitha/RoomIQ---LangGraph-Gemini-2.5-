"""
A2A / MCP-style tool layer.

Every agent interacts with the workplace world exclusively through these
tools rather than importing the ORM directly. Each tool has:
  - a clear typed input
  - a clear typed output (plain dict, JSON-serializable for agent state)
  - input validation
  - error handling (never raises out to the caller; returns {"error": ...})
  - logging via the module logger

This mirrors an MCP tool registry: tools are named, documented, callable
by name, and safe to expose to an LLM-driven planner.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as m
from app.database import repositories as repo

logger = logging.getLogger("roomiq.tools")


def _log(tool: str, **kwargs) -> None:
    logger.info("tool=%s args=%s", tool, kwargs)


def _err(tool: str, message: str) -> dict:
    logger.warning("tool_error=%s message=%s", tool, message)
    return {"error": message, "tool": tool}


# ---------------------------------------------------------------------
# Inventory / read tools
# ---------------------------------------------------------------------

def get_room_inventory(db: Session) -> dict:
    _log("get_room_inventory")
    rooms = repo.list_rooms(db)
    return {
        "rooms": [
            {
                "room_id": r.id,
                "room_name": r.room_name,
                "floor": r.floor,
                "floor_label": r.floor_label,
                "team_name": r.team_name,
                "capacity": r.capacity,
                "min_capacity": r.min_capacity,
                "max_capacity": r.max_capacity,
                "standing_capacity": r.standing_capacity,
                "chair_inventory": r.chair_inventory,
                "bench_count": r.bench_count,
                "is_executive": r.is_executive,
                "zone": r.zone,
                "room_type": r.room_type,
                "projector": r.projector_available,
                "video_conferencing": r.video_conferencing,
                "whiteboard": r.whiteboard,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
            }
            for r in rooms
        ]
    }


def get_desk_inventory(db: Session) -> dict:
    _log("get_desk_inventory")
    desks = repo.list_desks(db)
    return {
        "desks": [
            {
                "desk_id": d.id,
                "desk_code": d.desk_code,
                "floor": d.floor,
                "zone": d.zone,
                "desk_type": d.desk_type,
                "status": d.status,
            }
            for d in desks
        ]
    }


def get_bookings(db: Session, day: dt.date | None = None) -> dict:
    day = day or dt.date.today()
    _log("get_bookings", day=str(day))
    bookings = repo.list_bookings_for_day(db, day)
    return {
        "date": str(day),
        "bookings": [
            {
                "booking_id": b.id,
                "room_id": b.room_id,
                "title": b.title,
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "expected_attendees": b.expected_attendees,
                "status": b.status.value if hasattr(b.status, "value") else b.status,
            }
            for b in bookings
        ],
    }


def get_occupancy(db: Session, room_id: str | None = None) -> dict:
    _log("get_occupancy", room_id=room_id)
    if room_id:
        rec = repo.latest_occupancy(db, room_id)
        if rec is None:
            return _err("get_occupancy", f"No occupancy data for room {room_id}")
        return {
            "room_id": room_id,
            "detected_occupants": rec.detected_occupants,
            "status": rec.occupancy_status,
            "timestamp": rec.timestamp.isoformat(),
        }
    rooms = repo.list_rooms(db)
    out = []
    for r in rooms:
        rec = repo.latest_occupancy(db, r.id)
        if rec:
            out.append(
                {
                    "room_id": r.id,
                    "room_name": r.room_name,
                    "detected_occupants": rec.detected_occupants,
                    "status": rec.occupancy_status,
                    "timestamp": rec.timestamp.isoformat(),
                }
            )
    return {"occupancy": out}


# ---------------------------------------------------------------------
# Prediction tool
# ---------------------------------------------------------------------

def predict_demand(db: Session) -> dict:
    """Delegates to the prediction service (Pandas/Scikit-learn)."""
    from app.services.prediction_service import predict_demand as _predict

    _log("predict_demand")
    try:
        return _predict(db)
    except Exception as exc:  # pragma: no cover - defensive
        return _err("predict_demand", str(exc))


# ---------------------------------------------------------------------
# Search / matching tools
# ---------------------------------------------------------------------

def find_available_rooms(
    db: Session,
    *,
    day: dt.date,
    start: dt.datetime,
    end: dt.datetime,
    min_capacity: int = 1,
    require_projector: bool = False,
    require_video: bool = False,
    preferred_floor: int | None = None,
    preferred_zone: str | None = None,
) -> dict:
    _log("find_available_rooms", capacity=min_capacity, floor=preferred_floor)
    if end <= start:
        return _err("find_available_rooms", "end must be after start")

    candidates = []
    for room in repo.list_rooms(db):
        if room.capacity < min_capacity:
            continue
        if require_projector and not room.projector_available:
            continue
        if require_video and not room.video_conferencing:
            continue
        conflicts = detect_conflicts(db, room_id=room.id, start=start, end=end)
        if conflicts.get("conflict"):
            continue
        score = _score_room(room, min_capacity, preferred_floor, preferred_zone, require_projector, require_video)
        candidates.append({"room": room, "score": score})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return {
        "candidates": [
            {
                "room_id": c["room"].id,
                "room_name": c["room"].room_name,
                "floor": c["room"].floor,
                "zone": c["room"].zone,
                "capacity": c["room"].capacity,
                "match_score": c["score"],
            }
            for c in candidates[:5]
        ]
    }


def _score_room(room, min_capacity, preferred_floor, preferred_zone, require_projector, require_video) -> float:
    score = 60.0
    # Capacity fit: reward tight fit, penalize excessive oversize (waste).
    if room.capacity >= min_capacity:
        overage = room.capacity - min_capacity
        score += max(0, 20 - overage * 1.5)
    if require_projector and room.projector_available:
        score += 6
    if require_video and room.video_conferencing:
        score += 6
    if room.whiteboard:
        score += 2
    if preferred_floor is not None and room.floor == preferred_floor:
        score += 6
    if preferred_zone and room.zone == preferred_zone:
        score += 4
    return round(min(score, 99.0), 1)


def find_available_desks(db: Session, *, zone: str | None = None, floor: int | None = None) -> dict:
    _log("find_available_desks", zone=zone, floor=floor)
    desks = repo.list_desks(db)
    out = []
    for d in desks:
        if d.status != "AVAILABLE":
            continue
        if zone and d.zone != zone:
            continue
        if floor and d.floor != floor:
            continue
        out.append({"desk_id": d.id, "desk_code": d.desk_code, "floor": d.floor, "zone": d.zone})
    return {"available_desks": out}


def detect_conflicts(db: Session, *, room_id: str, start: dt.datetime, end: dt.datetime, exclude_booking_id: str | None = None) -> dict:
    if end <= start:
        return _err("detect_conflicts", "end must be after start")
    stmt = select(m.Booking).where(
        m.Booking.room_id == room_id,
        m.Booking.status.in_([m.BookingStatus.CONFIRMED, m.BookingStatus.REASSIGNED]),
        m.Booking.start_time < end,
        m.Booking.end_time > start,
    )
    rows = [b for b in db.scalars(stmt) if b.id != exclude_booking_id]
    return {"conflict": len(rows) > 0, "conflicting_bookings": [b.id for b in rows]}


# ---------------------------------------------------------------------
# Mutation tools
# ---------------------------------------------------------------------

def reallocate_space(
    db: Session,
    *,
    source_room_id: str | None,
    target_request_id: str | None,
    reason: str,
    expected_impact: str,
    confidence: float,
    run_id: str | None = None,
    entity_type: str = "ROOM",
) -> dict:
    _log("reallocate_space", source=source_room_id, target=target_request_id)
    event = m.ReallocationEvent(
        run_id=run_id,
        entity_type=entity_type,
        source_room_id=source_room_id,
        target_request_id=target_request_id,
        reason=reason,
        expected_impact=expected_impact,
        confidence=confidence,
        status="RECOMMENDED",
    )
    db.add(event)
    db.flush()
    return {"reallocation_id": event.id, "status": event.status}


def update_booking(
    db: Session,
    *,
    booking_id: str | None,
    new_room_id: str,
    start_time: dt.datetime,
    end_time: dt.datetime,
    reason: str,
    agent: str = "Booking & Scheduling Agent",
) -> dict:
    """Creates or reassigns a booking. Never a silent modification — always audited."""
    _log("update_booking", booking_id=booking_id, new_room_id=new_room_id)

    conflict = detect_conflicts(db, room_id=new_room_id, start=start_time, end=end_time, exclude_booking_id=booking_id)
    if conflict.get("conflict"):
        return _err("update_booking", f"Target room has a conflicting booking: {conflict['conflicting_bookings']}")

    if booking_id:
        booking = db.get(m.Booking, booking_id)
        if booking is None:
            return _err("update_booking", f"Booking {booking_id} not found")
        previous = f"Room {booking.room.room_name if booking.room else 'Unassigned'} {booking.start_time:%H:%M}-{booking.end_time:%H:%M}"
        booking.room_id = new_room_id
        booking.start_time = start_time
        booking.end_time = end_time
        booking.status = m.BookingStatus.REASSIGNED
        db.flush()
        new_state = f"Room {booking.room.room_name} {start_time:%H:%M}-{end_time:%H:%M}"
    else:
        return _err("update_booking", "booking_id is required to reassign; use create_booking to create new")

    repo.create_audit_log(
        db,
        agent=agent,
        action="Room Reassigned",
        entity=f"Booking #{booking.id}",
        previous_state=previous,
        new_state=new_state,
        reason=reason,
        confidence=0.0,
    )
    return {"booking_id": booking.id, "previous": previous, "new": new_state}


def create_notification(db: Session, *, user_id: str | None, category: str, title: str, message: str) -> dict:
    if category not in {c.value for c in m.NotificationCategory}:
        return _err("create_notification", f"Unknown category: {category}")
    _log("create_notification", category=category, user_id=user_id)
    n = repo.create_notification(db, user_id=user_id, category=category, title=title, message=message)
    return {"notification_id": n.id}


def calculate_utilization(db: Session, *, day: dt.date | None = None) -> dict:
    from app.services.occupancy_service import calculate_room_utilization

    day = day or dt.date.today()
    _log("calculate_utilization", day=str(day))
    return calculate_room_utilization(db, day)


def generate_optimization_report(db: Session, run_id: str) -> dict:
    run = db.get(m.AgentRun, run_id)
    if run is None:
        return _err("generate_optimization_report", f"Run {run_id} not found")
    return {
        "run_id": run.id,
        "status": run.status,
        "rooms_reallocated": run.rooms_reallocated,
        "desk_requests_resolved": run.desk_requests_resolved,
        "conflicts_resolved": run.conflicts_resolved,
        "unused_capacity_reduced_pct": run.unused_capacity_reduced_pct,
        "notifications_sent": run.notifications_sent,
        "summary": run.summary,
    }
