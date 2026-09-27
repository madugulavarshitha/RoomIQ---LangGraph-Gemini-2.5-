"""
Deterministic booking operations (availability, capacity, overlap —
all handled in Python, not by the LLM, per project rules).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.database import models as m
from app.services import tools


def create_booking(
    db: Session,
    *,
    user_id: str,
    room_id: str,
    title: str,
    start_time: dt.datetime,
    end_time: dt.datetime,
    expected_attendees: int,
    allocated_chairs: int | None = None,
    attendee_names: str = "",
    meeting_type: str = "General Meeting",
    requires_projector: bool = False,
    requires_video: bool = False,
) -> dict:
    if end_time <= start_time:
        return {"error": "End time must be after start time."}

    room = db.get(m.Room, room_id)
    if room is None:
        return {"error": "Room not found."}
    if expected_attendees > room.capacity:
        return {"error": f"{room.room_name} seats {room.capacity}; this meeting needs {expected_attendees}."}

    conflict = tools.detect_conflicts(db, room_id=room_id, start=start_time, end=end_time)
    if conflict.get("conflict"):
        return {"error": "This room is already booked for part of that time window."}

    if allocated_chairs is None:
        allocated_chairs = min(expected_attendees, room.chair_inventory) if room.chair_inventory else expected_attendees

    booking = m.Booking(
        user_id=user_id,
        room_id=room_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        expected_attendees=expected_attendees,
        allocated_chairs=allocated_chairs,
        attendee_names=attendee_names,
        meeting_type=meeting_type,
        requires_projector=requires_projector,
        requires_video=requires_video,
        status=m.BookingStatus.CONFIRMED,
    )
    db.add(booking)
    db.flush()

    from app.database import repositories as repo

    repo.create_audit_log(
        db,
        agent="Booking & Scheduling Agent",
        action="Booking Created",
        entity=f"Booking #{booking.id}",
        previous_state="—",
        new_state=f"Room {room.room_name} {start_time:%H:%M}-{end_time:%H:%M}",
        reason="User-initiated booking via Smart Booking.",
        confidence=1.0,
    )
    db.commit()
    return {"booking_id": booking.id, "room_name": room.room_name}


def cancel_booking(db: Session, booking_id: str, reason: str = "Cancelled by user") -> dict:
    booking = db.get(m.Booking, booking_id)
    if booking is None:
        return {"error": "Booking not found."}
    previous = booking.status.value
    booking.status = m.BookingStatus.CANCELLED
    db.flush()

    from app.database import repositories as repo

    repo.create_audit_log(
        db,
        agent="Booking & Scheduling Agent",
        action="Booking Cancelled",
        entity=f"Booking #{booking.id}",
        previous_state=previous,
        new_state="CANCELLED",
        reason=reason,
        confidence=1.0,
    )
    db.commit()
    return {"booking_id": booking.id, "status": "CANCELLED"}
