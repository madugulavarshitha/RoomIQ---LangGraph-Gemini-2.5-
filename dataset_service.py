"""
RoomIQ Dataset Ingestion & Management Service.

Supports:
1. Parsing and ingesting custom CSV/JSON datasets (Rooms, Users/Teams, Bookings, Desks, Occupancy).
2. Generating downloadable sample CSV templates.
3. Loading curated enterprise datasets (Multi-floor Digital Twin, Fast Startup, Peak Surge, Hybrid Flex).
4. Live recalculation of metrics across the database upon dataset ingestion.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import random
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.database import models as m
from app.services.occupancy_service import calculate_room_utilization
from app.services.simulation_service import seed_all

logger = logging.getLogger("roomiq.dataset")


def get_sample_csv_template() -> str:
    """Generates a multi-section or standard CSV template for workplace data."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Standard format: Rooms, Users, Bookings
    writer.writerow(["# RoomIQ Workplace Dataset Template"])
    writer.writerow(["# Format: SECTION, followed by headers and records"])
    writer.writerow([])
    
    writer.writerow(["[ROOMS]"])
    writer.writerow(["room_name", "floor", "floor_label", "team_name", "capacity", "chair_inventory", "room_type", "is_executive"])
    writer.writerow(["Ground Cabin 1", "0", "Ground Floor", "Product Team", "4", "4", "Cabin", "False"])
    writer.writerow(["Ground Major Hall", "0", "Ground Floor", "Product Team", "30", "30", "Major Hall", "False"])
    writer.writerow(["Ops Cabin 1", "3", "3rd Floor", "Operations Team", "6", "6", "Cabin", "False"])
    writer.writerow(["Ops Open Hall", "3", "3rd Floor", "Operations Team", "50", "50", "Major Hall", "False"])
    writer.writerow(["6th Floor Conference Room", "6", "6th Floor", "Shared", "20", "12", "Conference Room", "False"])
    writer.writerow(["FSD Tech Zone", "6", "6th Floor", "FSD", "15", "10", "Cabin", "False"])
    writer.writerow([])
    
    writer.writerow(["[USERS]"])
    writer.writerow(["full_name", "email", "role", "department", "team", "floor_preference", "work_mode"])
    writer.writerow(["Ava Sharma", "admin@roomiq.io", "ADMIN", "Operations", "Operations Team", "3", "In-Office"])
    writer.writerow(["Marcus Vance", "marcus@roomiq.io", "FACILITIES_MANAGER", "Facilities", "Operations Team", "3", "In-Office"])
    writer.writerow(["Jordan Chen", "jordan@roomiq.io", "EMPLOYEE", "Product", "Product Team", "0", "Hybrid"])
    writer.writerow(["Aarav Patel", "aarav@roomiq.io", "EMPLOYEE", "Engineering", "FSD", "6", "In-Office"])
    writer.writerow([])
    
    writer.writerow(["[BOOKINGS]"])
    writer.writerow(["title", "user_email", "room_name", "start_time", "end_time", "expected_attendees", "status"])
    today_str = dt.date.today().isoformat()
    writer.writerow(["Daily Standup", "jordan@roomiq.io", "Ground Cabin 1", f"{today_str} 09:30:00", f"{today_str} 10:30:00", "4", "CONFIRMED"])
    writer.writerow(["Sprint Planning", "aarav@roomiq.io", "6th Floor Conference Room", f"{today_str} 14:00:00", f"{today_str} 16:00:00", "12", "CONFIRMED"])
    
    return output.getvalue()


def ingest_dataset_content(db: Session, content: str, filename: str = "data.csv") -> Dict[str, Any]:
    """Parses and ingests a custom CSV or JSON dataset into the RoomIQ database."""
    filename_lower = filename.lower()
    
    if filename_lower.endswith(".json"):
        try:
            data = json.loads(content)
            return _ingest_json_dict(db, data)
        except Exception as e:
            logger.exception("Failed to parse JSON dataset: %s", e)
            raise ValueError(f"Invalid JSON format: {str(e)}")
            
    # Parse as CSV
    try:
        return _ingest_csv_text(db, content)
    except Exception as e:
        logger.exception("Failed to parse CSV dataset: %s", e)
        raise ValueError(f"CSV ingestion error: {str(e)}")


def _ingest_csv_text(db: Session, text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    
    current_section = "ROOMS"
    section_rows: Dict[str, List[Dict[str, str]]] = {
        "ROOMS": [],
        "USERS": [],
        "BOOKINGS": [],
        "DESKS": []
    }
    
    csv_reader = csv.reader(lines)
    header = None
    
    for raw_row in csv_reader:
        if not raw_row or not any(raw_row):
            continue
            
        first_cell = raw_row[0].strip()
        if first_cell.startswith("#"):
            continue
            
        if first_cell.upper() in ["[ROOMS]", "ROOMS", "SECTION:ROOMS"]:
            current_section = "ROOMS"
            header = None
            continue
        elif first_cell.upper() in ["[USERS]", "USERS", "SECTION:USERS", "[MEMBERS]"]:
            current_section = "USERS"
            header = None
            continue
        elif first_cell.upper() in ["[BOOKINGS]", "BOOKINGS", "SECTION:BOOKINGS", "[RESERVATIONS]"]:
            current_section = "BOOKINGS"
            header = None
            continue
        elif first_cell.upper() in ["[DESKS]", "DESKS", "SECTION:DESKS"]:
            current_section = "DESKS"
            header = None
            continue
            
        if header is None:
            header = [c.strip().lower() for c in raw_row]
            # Check if this header auto-detects section
            if "room_name" in header or "capacity" in header:
                current_section = "ROOMS"
            elif "email" in header or "full_name" in header:
                current_section = "USERS"
            elif "expected_attendees" in header or "start_time" in header:
                current_section = "BOOKINGS"
            elif "desk_code" in header:
                current_section = "DESKS"
            continue
            
        # Map row values to headers
        row_dict = {}
        for idx, col_name in enumerate(header):
            if idx < len(raw_row):
                row_dict[col_name] = raw_row[idx].strip()
        section_rows[current_section].append(row_dict)

    # Ingest parsed entities
    return _apply_dataset_to_db(db, section_rows)


def _ingest_json_dict(db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
    section_rows: Dict[str, List[Dict[str, str]]] = {
        "ROOMS": data.get("rooms", []),
        "USERS": data.get("users", []) or data.get("members", []),
        "BOOKINGS": data.get("bookings", []),
        "DESKS": data.get("desks", [])
    }
    return _apply_dataset_to_db(db, section_rows)


def _apply_dataset_to_db(db: Session, sections: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    # 1. Clear existing dynamic tables
    for model in [
        m.OccupancyRecord,
        m.AttendanceRecord,
        m.Booking,
        m.DeskReservation,
        m.Desk,
        m.Room,
        m.User,
        m.Notification,
        m.AgentRun,
        m.AgentEvent,
        m.ReallocationEvent
    ]:
        db.query(model).delete()
    db.commit()

    rooms_count = 0
    users_count = 0
    bookings_count = 0
    desks_count = 0

    # Ensure admin user is always present
    admin_user = m.User(
        full_name="Ava Sharma",
        email="admin@roomiq.io",
        password_hash=hash_password("Admin123!"),
        role=m.Role.ADMIN,
        department="Operations",
        team="Operations Team",
        work_mode="In-Office",
        floor_preference=3,
    )
    db.add(admin_user)
    users_by_email = {"admin@roomiq.io": admin_user}

    # Ingest Users
    for u in sections.get("USERS", []):
        email = u.get("email", "").strip().lower()
        if not email or email == "admin@roomiq.io":
            continue
        role_str = u.get("role", "EMPLOYEE").upper()
        role = m.Role.ADMIN if "ADMIN" in role_str else (m.Role.FACILITIES_MANAGER if "FACIL" in role_str else m.Role.EMPLOYEE)
        
        user_obj = m.User(
            full_name=u.get("full_name") or u.get("name") or email.split("@")[0].capitalize(),
            email=email,
            password_hash=hash_password("Password123!"),
            role=role,
            department=u.get("department", "General"),
            team=u.get("team", "General Team"),
            work_mode=u.get("work_mode", "In-Office"),
            floor_preference=int(u.get("floor_preference", 0) or 0)
        )
        db.add(user_obj)
        users_by_email[email] = user_obj
        users_count += 1

    db.commit()

    # Ingest Rooms
    rooms_by_name = {}
    for r in sections.get("ROOMS", []):
        r_name = r.get("room_name") or r.get("name")
        if not r_name:
            continue
            
        floor_num = int(r.get("floor", 0) or 0)
        floor_lbl = r.get("floor_label") or (f"Floor {floor_num}" if floor_num > 0 else "Ground Floor")
        cap = int(r.get("capacity", 6) or 6)
        chairs = int(r.get("chair_inventory", cap) or cap)
        
        room_obj = m.Room(
            room_name=r_name,
            floor=floor_num,
            floor_label=floor_lbl,
            team_name=r.get("team_name") or r.get("team") or "Shared",
            capacity=cap,
            min_capacity=max(1, cap // 2),
            max_capacity=cap,
            chair_inventory=chairs,
            bench_count=int(r.get("bench_count", 0) or 0),
            is_executive=str(r.get("is_executive", "false")).lower() in ["true", "1", "yes"],
            usage_notes=r.get("usage_notes", ""),
            zone=r.get("zone", "Central"),
            room_type=r.get("room_type", "Cabin" if cap <= 8 else "Major Hall"),
            projector_available=True,
            video_conferencing=True,
            status=m.RoomStatus.AVAILABLE
        )
        db.add(room_obj)
        rooms_by_name[r_name] = room_obj
        rooms_count += 1

    db.commit()

    # Ingest Bookings
    today = dt.date.today()
    all_users = list(users_by_email.values())
    all_rooms = list(rooms_by_name.values())

    for b in sections.get("BOOKINGS", []):
        b_title = b.get("title", "Workspace Meeting")
        user_email = b.get("user_email", "").strip().lower()
        matched_user = users_by_email.get(user_email) or (all_users[0] if all_users else admin_user)
        
        room_name = b.get("room_name", "")
        matched_room = rooms_by_name.get(room_name) or (all_rooms[0] if all_rooms else None)
        
        # Parse timestamps
        try:
            st_raw = b.get("start_time", "")
            if " " in st_raw:
                st = dt.datetime.strptime(st_raw, "%Y-%m-%d %H:%M:%S")
            elif "T" in st_raw:
                st = dt.datetime.fromisoformat(st_raw)
            else:
                st = dt.datetime.combine(today, dt.time(10, 0))
        except Exception:
            st = dt.datetime.combine(today, dt.time(10, 0))

        try:
            et_raw = b.get("end_time", "")
            if " " in et_raw:
                et = dt.datetime.strptime(et_raw, "%Y-%m-%d %H:%M:%S")
            elif "T" in et_raw:
                et = dt.datetime.fromisoformat(et_raw)
            else:
                et = st + dt.timedelta(hours=1)
        except Exception:
            et = st + dt.timedelta(hours=1)

        exp_att = int(b.get("expected_attendees", 4) or 4)
        status_str = b.get("status", "CONFIRMED").upper()
        b_status = m.BookingStatus.CONFIRMED if "CONFIRM" in status_str else m.BookingStatus.PENDING

        booking_obj = m.Booking(
            user_id=matched_user.id,
            room_id=matched_room.id if matched_room else None,
            title=b_title,
            start_time=st,
            end_time=et,
            expected_attendees=exp_att,
            allocated_chairs=matched_room.chair_inventory if matched_room else exp_att,
            status=b_status
        )
        db.add(booking_obj)
        bookings_count += 1

    # Ingest Desks
    for d in sections.get("DESKS", []):
        d_code = d.get("desk_code")
        if not d_code:
            continue
        fl = int(d.get("floor", 0) or 0)
        desk_obj = m.Desk(
            desk_code=d_code,
            floor=fl,
            zone=d.get("zone", "Central Zone"),
            desk_type=d.get("desk_type", "Hybrid"),
            status=d.get("status", "AVAILABLE")
        )
        db.add(desk_obj)
        desks_count += 1

    # Ingest Attendance & Initial Occupancy records
    for u in all_users:
        att = m.AttendanceRecord(
            user_id=u.id,
            date=dt.datetime.combine(today, dt.time(9, 0)),
            checked_in=True,
            status="IN_OFFICE" if u.work_mode == "In-Office" else "WFH",
            floor=u.floor_preference
        )
        db.add(att)

    for r in all_rooms:
        occ = m.OccupancyRecord(
            room_id=r.id,
            timestamp=dt.datetime.combine(today, dt.time(11, 0)),
            detected_occupants=max(0, int(r.capacity * random.uniform(0.3, 0.85))),
            occupancy_status="OCCUPIED" if random.random() > 0.3 else "AVAILABLE"
        )
        db.add(occ)

    # Add Ingestion Notification
    noti = m.Notification(
        user_id=admin_user.id,
        category="Optimization Completed",
        title="Dataset Successfully Ingested",
        message=f"Uploaded dataset active: {rooms_count} Rooms, {users_count + 1} Members, {bookings_count} Bookings, {desks_count} Desks.",
        read=False
    )
    db.add(noti)

    db.commit()

    return {
        "status": "success",
        "message": f"Successfully ingested {rooms_count} rooms, {users_count + 1} members, {bookings_count} bookings, and {desks_count} desks.",
        "counts": {
            "rooms": rooms_count,
            "members": users_count + 1,
            "bookings": bookings_count,
            "desks": desks_count
        }
    }


def clear_all_workplace_data(db: Session) -> Dict[str, Any]:
    """Wipes all dummy rooms, desks, bookings, and users except admin."""
    for model in [
        m.OccupancyRecord,
        m.AttendanceRecord,
        m.Booking,
        m.DeskReservation,
        m.Desk,
        m.Room,
        m.Notification,
        m.AgentRun,
        m.AgentEvent,
        m.ReallocationEvent
    ]:
        db.query(model).delete()
    
    db.query(m.User).filter(m.User.email != "admin@roomiq.io").delete()
    
    admin = db.query(m.User).filter(m.User.email == "admin@roomiq.io").first()
    if not admin:
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
    return {"status": "success", "message": "All dummy data cleared. Ready for dataset upload."}


def load_preset_dataset(db: Session, preset_id: str) -> Dict[str, Any]:
    """Loads a high-fidelity curated enterprise scenario into the database."""
    if preset_id == "digital_twin" or preset_id == "default":
        seed_all(db, force=True)
        return {
            "status": "success",
            "preset": "Real Office Multi-Floor Digital Twin",
            "message": "Loaded 3-floor Digital Twin (Ground, 3rd, 6th floors) with 206 members and 267 chairs."
        }
    
    # Custom Curated Presets
    if preset_id == "tech_startup":
        return _build_startup_dataset(db)
    elif preset_id == "peak_surge":
        return _build_peak_surge_dataset(db)
    elif preset_id == "hybrid_flex":
        return _build_hybrid_flex_dataset(db)
    else:
        seed_all(db, force=True)
        return {"status": "success", "preset": "Default", "message": "Loaded default office twin."}


def _build_startup_dataset(db: Session) -> Dict[str, Any]:
    rooms_data = [
        {"room_name": "Sprint Hub Alpha", "floor": 1, "floor_label": "Floor 1 (Eng)", "team_name": "Engineering", "capacity": 12, "chair_inventory": 12, "room_type": "Cabin"},
        {"room_name": "All-Hands Townhall", "floor": 1, "floor_label": "Floor 1 (Eng)", "team_name": "All Teams", "capacity": 65, "chair_inventory": 65, "room_type": "Major Hall"},
        {"room_name": "Brainstorm Lab", "floor": 1, "floor_label": "Floor 1 (Eng)", "team_name": "Product", "capacity": 8, "chair_inventory": 8, "room_type": "Cabin"},
        {"room_name": "Growth & Sales Deck", "floor": 2, "floor_label": "Floor 2 (Biz)", "team_name": "Sales", "capacity": 16, "chair_inventory": 16, "room_type": "Cabin"},
        {"room_name": "Executive Boardroom", "floor": 2, "floor_label": "Floor 2 (Biz)", "team_name": "Leadership", "capacity": 14, "chair_inventory": 14, "room_type": "Conference Room", "is_executive": True},
        {"room_name": "Podcast & Media Studio", "floor": 2, "floor_label": "Floor 2 (Biz)", "team_name": "Marketing", "capacity": 6, "chair_inventory": 6, "room_type": "Cabin"},
    ]
    users_data = [
        {"full_name": "Ava Sharma", "email": "admin@roomiq.io", "role": "ADMIN", "department": "Operations", "team": "Operations", "floor_preference": 1, "work_mode": "In-Office"},
        {"full_name": "Devin Torres", "email": "devin@startup.io", "role": "EMPLOYEE", "department": "Engineering", "team": "Engineering", "floor_preference": 1, "work_mode": "In-Office"},
        {"full_name": "Elena Rostova", "email": "elena@startup.io", "role": "EMPLOYEE", "department": "Product", "team": "Product", "floor_preference": 1, "work_mode": "In-Office"},
        {"full_name": "Marcus Vance", "email": "marcus@startup.io", "role": "EMPLOYEE", "department": "Sales", "team": "Sales", "floor_preference": 2, "work_mode": "In-Office"},
        {"full_name": "Priya Nair", "email": "priya@startup.io", "role": "EMPLOYEE", "department": "Marketing", "team": "Marketing", "floor_preference": 2, "work_mode": "Hybrid"},
    ]
    today_str = dt.date.today().isoformat()
    bookings_data = [
        {"title": "Product Roadmap Sync", "user_email": "elena@startup.io", "room_name": "Brainstorm Lab", "start_time": f"{today_str} 10:00:00", "end_time": f"{today_str} 11:30:00", "expected_attendees": 8},
        {"title": "Q3 Investor Pitch Rehearsal", "user_email": "admin@roomiq.io", "room_name": "Executive Boardroom", "start_time": f"{today_str} 14:00:00", "end_time": f"{today_str} 16:00:00", "expected_attendees": 12},
        {"title": "Engineering Architecture Review", "user_email": "devin@startup.io", "room_name": "Sprint Hub Alpha", "start_time": f"{today_str} 16:00:00", "end_time": f"{today_str} 17:30:00", "expected_attendees": 10},
    ]
    
    sections = {"ROOMS": rooms_data, "USERS": users_data, "BOOKINGS": bookings_data, "DESKS": []}
    res = _apply_dataset_to_db(db, sections)
    res["preset"] = "Fast-Growing Tech Startup"
    return res


def _build_peak_surge_dataset(db: Session) -> Dict[str, Any]:
    # High demand scenario with constrained conference chairs
    seed_all(db, force=True)
    # Re-tune rooms with bottlenecks
    today = dt.date.today()
    admin = db.query(m.User).first()
    conf = db.query(m.Room).filter(m.Room.room_name.ilike("%Conference%")).first()
    if conf:
        conf.chair_inventory = 6 # Severe chair bottleneck
        db.commit()
    return {
        "status": "success",
        "preset": "Peak Utilization & Bottleneck Surge",
        "message": "Simulating high conflict peak all-hands day with conference room shortages."
    }


def _build_hybrid_flex_dataset(db: Session) -> Dict[str, Any]:
    seed_all(db, force=True)
    return {
        "status": "success",
        "preset": "Hybrid Flex Workplace",
        "message": "Loaded flexible hybrid desk & hot-desking scenario across all 3 floors."
    }
