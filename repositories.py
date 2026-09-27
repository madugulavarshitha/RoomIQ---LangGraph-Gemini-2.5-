"""
Thin repository layer: reusable query helpers over the ORM models.
Keeping these in one place means agents and API routes never write
ad-hoc SQL/ORM queries inline, which keeps validation/logging consistent.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as m


def list_rooms(db: Session) -> list[m.Room]:
    return list(db.scalars(select(m.Room).order_by(m.Room.floor, m.Room.room_name)))


def get_room(db: Session, room_id: str) -> m.Room | None:
    return db.get(m.Room, room_id)


def list_desks(db: Session) -> list[m.Desk]:
    return list(db.scalars(select(m.Desk).order_by(m.Desk.floor, m.Desk.desk_code)))


def list_bookings_for_day(db: Session, day: dt.date) -> list[m.Booking]:
    start = dt.datetime.combine(day, dt.time.min)
    end = dt.datetime.combine(day, dt.time.max)
    stmt = select(m.Booking).where(
        m.Booking.start_time >= start,
        m.Booking.start_time <= end,
        m.Booking.status != m.BookingStatus.CANCELLED,
    )
    return list(db.scalars(stmt))


def active_bookings_for_room(db: Session, room_id: str, day: dt.date) -> list[m.Booking]:
    start = dt.datetime.combine(day, dt.time.min)
    end = dt.datetime.combine(day, dt.time.max)
    stmt = select(m.Booking).where(
        m.Booking.room_id == room_id,
        m.Booking.start_time >= start,
        m.Booking.start_time <= end,
        m.Booking.status.in_([m.BookingStatus.CONFIRMED, m.BookingStatus.REASSIGNED]),
    )
    return list(db.scalars(stmt))


def waiting_meeting_requests(db: Session) -> list[m.MeetingRequest]:
    stmt = select(m.MeetingRequest).where(m.MeetingRequest.status == "WAITING")
    return list(db.scalars(stmt))


def waiting_desk_requests(db: Session) -> list[m.DeskReservation]:
    stmt = select(m.DeskReservation).where(m.DeskReservation.status == "WAITING")
    return list(db.scalars(stmt))


def latest_occupancy(db: Session, room_id: str) -> m.OccupancyRecord | None:
    stmt = (
        select(m.OccupancyRecord)
        .where(m.OccupancyRecord.room_id == room_id)
        .order_by(m.OccupancyRecord.timestamp.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def create_notification(db: Session, *, user_id: str | None, category: str, title: str, message: str) -> m.Notification:
    n = m.Notification(user_id=user_id, category=category, title=title, message=message)
    db.add(n)
    db.flush()
    return n


def create_audit_log(
    db: Session,
    *,
    agent: str,
    action: str,
    entity: str,
    previous_state: str,
    new_state: str,
    reason: str,
    confidence: float,
) -> m.AuditLog:
    log = m.AuditLog(
        agent=agent,
        action=action,
        entity=entity,
        previous_state=previous_state,
        new_state=new_state,
        reason=reason,
        confidence=confidence,
    )
    db.add(log)
    db.flush()
    return log
