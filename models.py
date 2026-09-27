"""
RoomIQ relational schema.

Tables: users, rooms, desks, bookings, desk_reservations, occupancy_records,
attendance_records, meeting_requests, notifications, agent_runs,
agent_events, utilization_metrics, reallocation_events, audit_logs.
"""
from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def now() -> dt.datetime:
    return dt.datetime.utcnow()


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    FACILITIES_MANAGER = "FACILITIES_MANAGER"
    EMPLOYEE = "EMPLOYEE"


class RoomStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    OCCUPIED = "OCCUPIED"
    UNDERUTILIZED = "UNDERUTILIZED"
    CONFLICT = "CONFLICT"


class BookingStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REASSIGNED = "REASSIGNED"
    PENDING = "PENDING"


class NotificationCategory(str, enum.Enum):
    ROOM_REASSIGNED = "Room Reassigned"
    BOOKING_UPDATED = "Booking Updated"
    CONFLICT_DETECTED = "Conflict Detected"
    SPACE_AVAILABLE = "Space Available"
    OPTIMIZATION_COMPLETED = "Optimization Completed"
    DESK_REASSIGNED = "Desk Reassigned"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.EMPLOYEE)
    department: Mapped[str] = mapped_column(String(80), default="General")
    team: Mapped[str] = mapped_column(String(80), default="General")
    work_mode: Mapped[str] = mapped_column(String(40), default="In-Office")  # In-Office, Hybrid, WFH
    floor_preference: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    room_name: Mapped[str] = mapped_column(String(80), unique=True)
    floor: Mapped[int] = mapped_column(Integer)  # 0 = Ground Floor, 3 = 3rd Floor, 6 = 6th Floor
    floor_label: Mapped[str] = mapped_column(String(40), default="Ground Floor")
    team_name: Mapped[str] = mapped_column(String(80), default="Shared")
    capacity: Mapped[int] = mapped_column(Integer)  # Seated capacity
    min_capacity: Mapped[int] = mapped_column(Integer, default=1)
    max_capacity: Mapped[int] = mapped_column(Integer, default=1)
    standing_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    chair_inventory: Mapped[int] = mapped_column(Integer, default=0)  # Currently tracked chairs
    bench_count: Mapped[int] = mapped_column(Integer, default=0)
    is_executive: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_notes: Mapped[str] = mapped_column(String(255), default="")
    zone: Mapped[str] = mapped_column(String(40), default="Central")
    room_type: Mapped[str] = mapped_column(String(40), default="Meeting Room")
    projector_available: Mapped[bool] = mapped_column(Boolean, default=False)
    video_conferencing: Mapped[bool] = mapped_column(Boolean, default=False)
    whiteboard: Mapped[bool] = mapped_column(Boolean, default=False)
    accessibility: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[RoomStatus] = mapped_column(Enum(RoomStatus), default=RoomStatus.AVAILABLE)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")


class Desk(Base):
    __tablename__ = "desks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    desk_code: Mapped[str] = mapped_column(String(20), unique=True)
    floor: Mapped[int] = mapped_column(Integer)
    zone: Mapped[str] = mapped_column(String(40))
    desk_type: Mapped[str] = mapped_column(String(40), default="Hybrid")
    amenities: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")


class DeskReservation(Base):
    __tablename__ = "desk_reservations"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    desk_id: Mapped[str | None] = mapped_column(ForeignKey("desks.id"), nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reservation_date: Mapped[dt.date] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="WAITING")  # WAITING, CONFIRMED, CANCELLED
    zone_preference: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    start_time: Mapped[dt.datetime] = mapped_column(DateTime)
    end_time: Mapped[dt.datetime] = mapped_column(DateTime)
    expected_attendees: Mapped[int] = mapped_column(Integer, default=1)
    allocated_chairs: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    attendee_names: Mapped[str | None] = mapped_column(String(500), nullable=True, default="")
    attended_names: Mapped[str | None] = mapped_column(String(500), nullable=True, default="")
    absent_names: Mapped[str | None] = mapped_column(String(500), nullable=True, default="")
    actual_attendees_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    meeting_type: Mapped[str | None] = mapped_column(String(60), nullable=True, default="General Meeting")
    meeting_outcome: Mapped[str | None] = mapped_column(String(40), nullable=True, default="COMPLETED")
    requires_projector: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_video: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.CONFIRMED)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    user: Mapped["User"] = relationship(back_populates="bookings")
    room: Mapped["Room"] = relationship(back_populates="bookings")


class OccupancyRecord(Base):
    __tablename__ = "occupancy_records"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    detected_occupants: Mapped[int] = mapped_column(Integer, default=0)
    occupancy_status: Mapped[str] = mapped_column(String(30), default="EMPTY")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    date: Mapped[dt.date] = mapped_column(DateTime)
    checked_in: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="IN_OFFICE")  # IN_OFFICE, WFH, ON_LEAVE
    floor: Mapped[int] = mapped_column(Integer, default=0)


class MeetingRequest(Base):
    __tablename__ = "meeting_requests"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(160))
    participants: Mapped[int] = mapped_column(Integer, default=1)
    requires_projector: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_video: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_zone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    start_time: Mapped[dt.datetime] = mapped_column(DateTime)
    end_time: Mapped[dt.datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="WAITING")
    matched_room_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    workflow: Mapped[str] = mapped_column(String(80), default="workplace_optimization")
    triggered_by: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING, COMPLETED, ERROR
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    rooms_reallocated: Mapped[int] = mapped_column(Integer, default=0)
    desk_requests_resolved: Mapped[int] = mapped_column(Integer, default=0)
    conflicts_resolved: Mapped[int] = mapped_column(Integer, default=0)
    unused_capacity_reduced_pct: Mapped[float] = mapped_column(Float, default=0.0)
    notifications_sent: Mapped[int] = mapped_column(Integer, default=0)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"))
    agent_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="IDLE")
    action: Mapped[str] = mapped_column(String(200), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class UtilizationMetric(Base):
    __tablename__ = "utilization_metrics"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    entity_type: Mapped[str] = mapped_column(String(20))  # ROOM, DESK, FLOOR
    entity_id: Mapped[str] = mapped_column(String(40))
    date: Mapped[dt.date] = mapped_column(DateTime)
    booked_hours: Mapped[float] = mapped_column(Float, default=0.0)
    occupied_hours: Mapped[float] = mapped_column(Float, default=0.0)
    utilization_pct: Mapped[float] = mapped_column(Float, default=0.0)


class ReallocationEvent(Base):
    __tablename__ = "reallocation_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(20), default="ROOM")  # ROOM, DESK
    source_room_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    target_request_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    expected_impact: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="RECOMMENDED")  # RECOMMENDED, APPLIED, REJECTED
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    agent: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    entity: Mapped[str] = mapped_column(String(160))
    previous_state: Mapped[str] = mapped_column(Text, default="")
    new_state: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
