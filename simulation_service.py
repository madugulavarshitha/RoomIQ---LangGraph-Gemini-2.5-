"""
Real Office Workplace Intelligence Simulation & Seeding Service.

Transforms RoomIQ into an exact digital twin of the real office:
- Ground Floor (Product Team: 35 members, 50 chairs, 5 cabins + Major Hall)
- 3rd Floor (Operations Team: 75 members, 80 chairs, 6 cabins + 4-bench Major Hall)
- 6th Floor (Technical Block: Conf Room [15/20 cap vs 6 chairs], CEO + 2 Exec cabins,
  FSD [15 members vs 10 chairs & 8-12 cap], Salesforce [15 members, 28 chairs, 15-20 cap, 2 benches],
  ServiceNow [29 members, 35 chairs, 3 cabins + 2-bench hall],
  AI / Tech [38 members, 46 chairs, 3 cabins + hall],
  Marketing [9 members, 12 chairs, 2 cabins + hall])
"""
from __future__ import annotations

import datetime as dt
import random

from faker import Faker
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.database import models as m

SEED = 42
fake = Faker()

FLOOR_MAP = {
    0: "Ground Floor",
    3: "3rd Floor",
    6: "6th Floor",
}

TEAM_METRICS = {
    "Product Team": {"floor": 0, "active_members": 35, "total_chairs": 50},
    "Operations Team": {"floor": 3, "active_members": 75, "total_chairs": 80},
    "FSD": {"floor": 6, "active_members": 15, "total_chairs": 10},
    "Salesforce": {"floor": 6, "active_members": 15, "total_chairs": 28},
    "ServiceNow": {"floor": 6, "active_members": 29, "total_chairs": 35},
    "AI / Technical Team": {"floor": 6, "active_members": 28, "total_chairs": 46},
    "Marketing": {"floor": 6, "active_members": 9, "total_chairs": 12},
}


def _demo_scenario_date() -> dt.date:
    return dt.date.today()


def seed_all(db: Session, *, force: bool = False) -> None:
    existing = db.query(m.User).count()
    if existing and not force:
        return
    if force or existing:
        _wipe(db)

    random.seed(SEED)
    Faker.seed(SEED)

    users = _seed_users(db)
    rooms = _seed_rooms(db)
    desks = _seed_desks(db)
    db.commit()

    _seed_historical_bookings(db, users, rooms)
    _seed_monday_scenario(db, users, rooms, desks)
    _seed_attendance(db, users)
    db.commit()


def _wipe(db: Session) -> None:
    for model in [
        m.AuditLog,
        m.ReallocationEvent,
        m.AgentEvent,
        m.AgentRun,
        m.UtilizationMetric,
        m.Notification,
        m.MeetingRequest,
        m.AttendanceRecord,
        m.OccupancyRecord,
        m.DeskReservation,
        m.Booking,
        m.Desk,
        m.Room,
        m.User,
    ]:
        db.query(model).delete()
    db.commit()


def _seed_users(db: Session) -> list[m.User]:
    users = []

    # 1. Primary demo accounts (Ava & Marcus -> Ops, Jordan -> Product)
    admin = m.User(
        full_name="Ava Sharma",
        email="admin@roomiq.io",
        password_hash=hash_password("Admin123!"),
        role=m.Role.ADMIN,
        department="Operations",
        team="Operations Team",
        work_mode="In-Office",
        floor_preference=3,
    )
    fm = m.User(
        full_name="Marcus Lee",
        email="facilities@roomiq.io",
        password_hash=hash_password("Facilities123!"),
        role=m.Role.FACILITIES_MANAGER,
        department="Operations",
        team="Operations Team",
        work_mode="In-Office",
        floor_preference=3,
    )
    employee = m.User(
        full_name="Jordan Blake",
        email="employee@roomiq.io",
        password_hash=hash_password("Employee123!"),
        role=m.Role.EMPLOYEE,
        department="Product",
        team="Product Team",
        work_mode="In-Office",
        floor_preference=0,
    )
    users.extend([admin, fm, employee])
    db.add_all([admin, fm, employee])

    # 2. Seed exact active headcount per team (206 total members: 35 + 75 + 15 + 15 + 29 + 28 + 9 = 206)
    team_counts = {
        "Product Team": (34, 0, "Product"),
        "Operations Team": (73, 3, "Operations"),
        "FSD": (15, 6, "Engineering"),
        "Salesforce": (15, 6, "Enterprise Apps"),
        "ServiceNow": (29, 6, "IT & Workflows"),
        "AI / Technical Team": (38, 6, "AI & Tech"),
        "Marketing": (9, 6, "Marketing"),
    }

    for team_name, (count, floor, dept) in team_counts.items():
        for _ in range(count):
            work_mode = random.choices(["In-Office", "Hybrid", "WFH"], weights=[0.75, 0.15, 0.10])[0]
            u = m.User(
                full_name=fake.name(),
                email=fake.unique.company_email(),
                password_hash=hash_password("Employee123!", rounds=4),
                role=m.Role.EMPLOYEE,
                department=dept,
                team=team_name,
                work_mode=work_mode,
                floor_preference=floor,
            )
            users.append(u)
            db.add(u)

    db.flush()
    return users


REAL_SPACES_SPEC = [
    # -------------------------------------------------------------
    # GROUND FLOOR — PRODUCT TEAM (35 members, 50 chairs)
    # -------------------------------------------------------------
    {
        "room_name": "Ground Floor — Cabin 1",
        "floor": 0,
        "floor_label": "Ground Floor",
        "team_name": "Product Team",
        "room_type": "Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 5,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Ground Hub",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Product team cabin (4–5 cap)",
    },
    {
        "room_name": "Ground Floor — Cabin 2",
        "floor": 0,
        "floor_label": "Ground Floor",
        "team_name": "Product Team",
        "room_type": "Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 5,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Ground Hub",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Product team cabin (4–5 cap)",
    },
    {
        "room_name": "Ground Floor — Cabin 3",
        "floor": 0,
        "floor_label": "Ground Floor",
        "team_name": "Product Team",
        "room_type": "Cabin",
        "capacity": 3,
        "min_capacity": 2,
        "max_capacity": 3,
        "standing_capacity": None,
        "chair_inventory": 3,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Ground Hub",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Product focus cabin (2–3 cap)",
    },
    {
        "room_name": "Ground Floor — Cabin 4",
        "floor": 0,
        "floor_label": "Ground Floor",
        "team_name": "Product Team",
        "room_type": "Cabin",
        "capacity": 3,
        "min_capacity": 2,
        "max_capacity": 3,
        "standing_capacity": None,
        "chair_inventory": 3,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Ground Hub",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Product focus cabin (2–3 cap)",
    },
    {
        "room_name": "Ground Floor — Cabin 5",
        "floor": 0,
        "floor_label": "Ground Floor",
        "team_name": "Product Team",
        "room_type": "Cabin",
        "capacity": 3,
        "min_capacity": 2,
        "max_capacity": 3,
        "standing_capacity": None,
        "chair_inventory": 3,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Ground Hub",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Product focus cabin (2–3 cap)",
    },
    {
        "room_name": "Ground Floor — Major Hall",
        "floor": 0,
        "floor_label": "Ground Floor",
        "team_name": "Product Team",
        "room_type": "Major Hall",
        "capacity": 15,
        "min_capacity": 10,
        "max_capacity": 15,
        "standing_capacity": 25,
        "chair_inventory": 31,  # 5+5+3+3+3 + 31 = 50 chairs total for Product
        "bench_count": 2,
        "is_executive": False,
        "zone": "Ground Hub",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Primary Product Team working area & flexible collaboration / meeting space (10–15 meeting capacity)",
    },

    # -------------------------------------------------------------
    # THIRD FLOOR — OPERATIONS TEAM (75 members, 80 chairs)
    # -------------------------------------------------------------
    {
        "room_name": "3rd Floor — Ops Cabin 1",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Cabin",
        "capacity": 8,
        "min_capacity": 7,
        "max_capacity": 8,
        "standing_capacity": None,
        "chair_inventory": 8,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Large Ops cabin (7–8 cap)",
    },
    {
        "room_name": "3rd Floor — Ops Cabin 2",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Cabin",
        "capacity": 8,
        "min_capacity": 7,
        "max_capacity": 8,
        "standing_capacity": None,
        "chair_inventory": 8,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Large Ops cabin (7–8 cap)",
    },
    {
        "room_name": "3rd Floor — Ops Cabin 3",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Cabin",
        "capacity": 4,
        "min_capacity": 2,
        "max_capacity": 4,
        "standing_capacity": None,
        "chair_inventory": 4,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Ops coordination cabin (2–4 cap)",
    },
    {
        "room_name": "3rd Floor — Ops Cabin 4",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Cabin",
        "capacity": 4,
        "min_capacity": 2,
        "max_capacity": 4,
        "standing_capacity": None,
        "chair_inventory": 4,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Ops coordination cabin (2–4 cap)",
    },
    {
        "room_name": "3rd Floor — Ops Cabin 5",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Cabin",
        "capacity": 4,
        "min_capacity": 2,
        "max_capacity": 4,
        "standing_capacity": None,
        "chair_inventory": 4,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Ops coordination cabin (2–4 cap)",
    },
    {
        "room_name": "3rd Floor — Ops Cabin 6",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Cabin",
        "capacity": 4,
        "min_capacity": 2,
        "max_capacity": 4,
        "standing_capacity": None,
        "chair_inventory": 4,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Ops coordination cabin (2–4 cap)",
    },
    {
        "room_name": "3rd Floor — Operations Major Hall",
        "floor": 3,
        "floor_label": "3rd Floor",
        "team_name": "Operations Team",
        "room_type": "Major Hall",
        "capacity": 50,
        "min_capacity": 40,
        "max_capacity": 50,
        "standing_capacity": 60,
        "chair_inventory": 48,  # 8+8+4+4+4+4 + 48 = 80 chairs total for Operations
        "bench_count": 4,
        "is_executive": False,
        "zone": "Operations Block",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Main Operations working area with 4 benches; 40–50 event capacity for team meetings, projector sessions, training, workshops, overflow, events",
    },

    # -------------------------------------------------------------
    # SIXTH FLOOR — TECHNICAL BLOCK & EXECUTIVE (9 areas)
    # -------------------------------------------------------------
    # 1. Conference Room
    {
        "room_name": "6th Floor — Conference Room",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Shared",
        "room_type": "Conference Room",
        "capacity": 15,  # Seated room capacity
        "min_capacity": 15,
        "max_capacity": 15,
        "standing_capacity": 20,  # Standing room capacity
        "chair_inventory": 6,  # Tracked chairs (Capacity Anomaly!)
        "bench_count": 0,
        "is_executive": False,
        "zone": "Executive & Shared",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Primary executive & all-hands conference room (15 seated, 20 standing, 6 tracked chairs)",
    },
    # 2. CEO Cabin
    {
        "room_name": "6th Floor — CEO Cabin",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Executive",
        "room_type": "Executive Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 0,
        "bench_count": 0,
        "is_executive": True,
        "zone": "Executive & Shared",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Executive / meeting / temporary use cabin (4–5 cap)",
    },
    # 3. Executive Cabin 1
    {
        "room_name": "6th Floor — Executive Cabin 1",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Executive",
        "room_type": "Executive Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 0,
        "bench_count": 0,
        "is_executive": True,
        "zone": "Executive & Shared",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Executive / meeting / temporary use cabin (4–5 cap)",
    },
    # 4. Executive Cabin 2
    {
        "room_name": "6th Floor — Executive Cabin 2",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Executive",
        "room_type": "Executive Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 0,
        "bench_count": 0,
        "is_executive": True,
        "zone": "Executive & Shared",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Executive / meeting / temporary use cabin (4–5 cap)",
    },
    # 5. FSD Room (Full Stack Development - 15 members, 10 chairs, 8-12 cap)
    {
        "room_name": "6th Floor — FSD Room",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "FSD",
        "room_type": "Technical Room",
        "capacity": 12,
        "min_capacity": 8,
        "max_capacity": 12,
        "standing_capacity": None,
        "chair_inventory": 10,  # 15 active members vs 10 chairs vs 8-12 cap (Shortage Warning!)
        "bench_count": 1,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "FSD Room: 15 active members, 10 tracked chairs, 8–12 capacity (Potential shortage)",
    },
    # 6. Salesforce Room (15 members, 28 chairs, 2 benches, 15-20 usable capacity)
    {
        "room_name": "6th Floor — Salesforce Hall",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Salesforce",
        "room_type": "Hall",
        "capacity": 20,
        "min_capacity": 15,
        "max_capacity": 20,
        "standing_capacity": 25,
        "chair_inventory": 28,  # Excess chairs (28) vs practical space (15-20)
        "bench_count": 2,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Salesforce Large Hall: 2 benches, 15 active members, 28 chairs, 15–20 practical working/meeting capacity",
    },
    # 7. ServiceNow (29 members, 35 chairs, 3 cabins + 1 hall)
    {
        "room_name": "6th Floor — ServiceNow Cabin 1",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "ServiceNow",
        "room_type": "Cabin",
        "capacity": 6,
        "min_capacity": 4,
        "max_capacity": 6,
        "standing_capacity": None,
        "chair_inventory": 6,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "ServiceNow cabin (4–6 cap)",
    },
    {
        "room_name": "6th Floor — ServiceNow Cabin 2",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "ServiceNow",
        "room_type": "Cabin",
        "capacity": 6,
        "min_capacity": 4,
        "max_capacity": 6,
        "standing_capacity": None,
        "chair_inventory": 6,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "ServiceNow cabin (4–6 cap)",
    },
    {
        "room_name": "6th Floor — ServiceNow Cabin 3",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "ServiceNow",
        "room_type": "Cabin",
        "capacity": 6,
        "min_capacity": 4,
        "max_capacity": 6,
        "standing_capacity": None,
        "chair_inventory": 6,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "ServiceNow cabin (4–6 cap)",
    },
    {
        "room_name": "6th Floor — ServiceNow Hall",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "ServiceNow",
        "room_type": "Hall",
        "capacity": 25,
        "min_capacity": 20,
        "max_capacity": 25,
        "standing_capacity": 30,
        "chair_inventory": 17,  # 6+6+6 + 17 = 35 chairs total for ServiceNow
        "bench_count": 2,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "ServiceNow Hall: 2 benches, 20–25 capacity for larger team meetings, training sessions and collaboration",
    },
    # 8. AI / Technical Team (38 members, 46 chairs, 3 cabins + 1 hall)
    {
        "room_name": "6th Floor — AI / Tech Cabin 1",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "AI / Technical Team",
        "room_type": "Cabin",
        "capacity": 8,
        "min_capacity": 6,
        "max_capacity": 8,
        "standing_capacity": None,
        "chair_inventory": 8,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "AI / Technical Team large cabin (6–8 cap)",
    },
    {
        "room_name": "6th Floor — AI / Tech Cabin 2",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "AI / Technical Team",
        "room_type": "Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 5,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "AI / Technical Team cabin (4–5 cap)",
    },
    {
        "room_name": "6th Floor — AI / Tech Cabin 3",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "AI / Technical Team",
        "room_type": "Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 5,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "AI / Technical Team cabin (4–5 cap)",
    },
    {
        "room_name": "6th Floor — AI / Tech Hall",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "AI / Technical Team",
        "room_type": "Hall",
        "capacity": 35,
        "min_capacity": 30,
        "max_capacity": 35,
        "standing_capacity": 45,
        "chair_inventory": 28,  # 8+5+5 + 28 = 46 chairs total for AI/Tech
        "bench_count": 3,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": True,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "AI / Tech Hall with benches, 30–35 capacity for technical collaboration and team sessions",
    },
    # 9. Marketing (9 members, 12 chairs, 2 cabins + 1 hall)
    {
        "room_name": "6th Floor — Marketing Cabin 1",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Marketing",
        "room_type": "Cabin",
        "capacity": 8,
        "min_capacity": 7,
        "max_capacity": 8,
        "standing_capacity": None,
        "chair_inventory": 8,
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": True,
        "whiteboard": True,
        "usage_notes": "Marketing campaign cabin (7–8 cap)",
    },
    {
        "room_name": "6th Floor — Marketing Cabin 2",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Marketing",
        "room_type": "Cabin",
        "capacity": 5,
        "min_capacity": 4,
        "max_capacity": 5,
        "standing_capacity": None,
        "chair_inventory": 4,  # 8+4 = 12 chairs total for Marketing
        "bench_count": 0,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Marketing focus cabin (4–5 cap)",
    },
    {
        "room_name": "6th Floor — Marketing Hall",
        "floor": 6,
        "floor_label": "6th Floor",
        "team_name": "Marketing",
        "room_type": "Hall",
        "capacity": 7,
        "min_capacity": 6,
        "max_capacity": 7,
        "standing_capacity": 10,
        "chair_inventory": 0,  # Uses shared cabin chairs or flexible space
        "bench_count": 1,
        "is_executive": False,
        "zone": "Technical Block",
        "projector_available": False,
        "video_conferencing": False,
        "whiteboard": True,
        "usage_notes": "Marketing collaboration hall (6–7 capacity)",
    },
]


def _seed_rooms(db: Session) -> list[m.Room]:
    rooms = []
    for spec in REAL_SPACES_SPEC:
        room = m.Room(
            room_name=spec["room_name"],
            floor=spec["floor"],
            floor_label=spec["floor_label"],
            team_name=spec["team_name"],
            room_type=spec["room_type"],
            capacity=spec["capacity"],
            min_capacity=spec["min_capacity"],
            max_capacity=spec["max_capacity"],
            standing_capacity=spec["standing_capacity"],
            chair_inventory=spec["chair_inventory"],
            bench_count=spec["bench_count"],
            is_executive=spec["is_executive"],
            zone=spec["zone"],
            projector_available=spec["projector_available"],
            video_conferencing=spec["video_conferencing"],
            whiteboard=spec["whiteboard"],
            accessibility=True,
            usage_notes=spec["usage_notes"],
            status=m.RoomStatus.AVAILABLE,
        )
        rooms.append(room)
        db.add(room)
    db.flush()
    return rooms


def _seed_desks(db: Session) -> list[m.Desk]:
    """Seed individual workstation / bench positions across the 3 floors."""
    desks = []
    counter = 1

    bench_allocations = [
        (0, "Ground Hub — Product Benches", 16),
        (3, "Operations Block — Bench 1 & 2", 24),
        (3, "Operations Block — Bench 3 & 4", 24),
        (6, "Technical Block — FSD & Salesforce Benches", 16),
        (6, "Technical Block — ServiceNow & AI Benches", 20),
    ]

    for floor, zone, count in bench_allocations:
        for i in range(count):
            desk = m.Desk(
                desk_code=f"FL{floor}-D{counter:03d}",
                floor=floor,
                zone=zone,
                desk_type=random.choice(["Hybrid Bench", "Dedicated Workstation", "Collaboration Pod", "Quiet Bench"]),
                amenities=random.choice([
                    "Dual 4K monitor, USB-C dock",
                    "Ergonomic chair, single monitor",
                    "Standing converter, dual dock",
                    "Dock, whiteboard nearby",
                ]),
                status=random.choices(["AVAILABLE", "RESERVED"], weights=[0.65, 0.35])[0],
            )
            desks.append(desk)
            db.add(desk)
            counter += 1

    db.flush()
    return desks


def _seed_historical_bookings(db: Session, users: list[m.User], rooms: list[m.Room]) -> None:
    # Historical meetings data removed per user request
    pass


def _seed_monday_scenario(db: Session, users: list[m.User], rooms: list[m.Room], desks: list[m.Desk]) -> None:
    monday = _demo_scenario_date()
    now = dt.datetime.utcnow()
    story_start = now - dt.timedelta(minutes=25)

    # Pick large halls/rooms for booked-but-unused demonstration
    target_underused_rooms = [
        r for r in rooms
        if r.room_name in (
            "3rd Floor — Operations Major Hall",
            "Ground Floor — Major Hall",
            "6th Floor — AI / Tech Hall",
            "6th Floor — Conference Room",
        )
    ]
    if not target_underused_rooms:
        target_underused_rooms = rooms[:4]

    for room in target_underused_rooms:
        start = story_start
        end = start + dt.timedelta(hours=6)
        user = random.choice(users)
        booking = m.Booking(
            user_id=user.id,
            room_id=room.id,
            title=f"{room.team_name} — Strategic Block & All Day Hold",
            start_time=start,
            end_time=end,
            expected_attendees=min(room.capacity, 15),
            requires_projector=True,
            requires_video=True,
            status=m.BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        # Sensor detects 0 occupants right now -> triggers UNDERUTILIZED
        occ = m.OccupancyRecord(
            room_id=room.id,
            timestamp=now,
            detected_occupants=0,
            occupancy_status="EMPTY",
        )
        db.add(occ)

    # Active utilized cabins for contrast
    active_sample_rooms = [r for r in rooms if r not in target_underused_rooms][:6]
    for room in active_sample_rooms:
        start = now - dt.timedelta(minutes=15)
        end = start + dt.timedelta(hours=1)
        booking = m.Booking(
            user_id=random.choice(users).id,
            room_id=room.id,
            title=f"{room.team_name} Active Standup",
            start_time=start,
            end_time=end,
            expected_attendees=min(room.capacity, 4),
            status=m.BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()
        occ = m.OccupancyRecord(
            room_id=room.id,
            timestamp=now,
            detected_occupants=min(room.capacity, max(2, room.capacity - 1)),
            occupancy_status="OCCUPIED",
        )
        db.add(occ)

    # Waiting requests requiring room reallocations
    meeting_titles = [
        ("FSD incident response & cross-team triage for 8 engineers with video conferencing.", 8, True, True),
        ("Product roadmap & UI design critique for 6 participants with whiteboard.", 6, False, False),
        ("Operations executive review for 10 leads requiring projector.", 10, True, False),
    ]
    for text, participants, proj, video in meeting_titles:
        mr = m.MeetingRequest(
            user_id=random.choice(users).id,
            raw_text=text,
            title=text.split(".")[0],
            participants=participants,
            requires_projector=proj,
            requires_video=video,
            start_time=now,
            end_time=now + dt.timedelta(hours=1),
            status="WAITING",
        )
        db.add(mr)

    # Waiting desk requests
    for _ in range(8):
        dr = m.DeskReservation(
            desk_id=None,
            user_id=random.choice(users).id,
            reservation_date=dt.datetime.combine(monday, dt.time.min),
            status="WAITING",
            zone_preference=random.choice(["Ground Hub", "Operations Block", "Technical Block"]),
        )
        db.add(dr)

    db.commit()


def _seed_attendance(db: Session, users: list[m.User]) -> None:
    monday = _demo_scenario_date()
    for user in users:
        # Respect user's work_mode
        if user.work_mode == "In-Office":
            status = "IN_OFFICE" if random.random() > 0.08 else "ON_LEAVE"
        elif user.work_mode == "Hybrid":
            status = random.choices(["IN_OFFICE", "WFH", "ON_LEAVE"], weights=[0.6, 0.35, 0.05])[0]
        else:
            status = "WFH"

        db.add(
            m.AttendanceRecord(
                user_id=user.id,
                date=dt.datetime.combine(monday, dt.time.min),
                checked_in=(status == "IN_OFFICE"),
                status=status,
                floor=user.floor_preference,
            )
        )
    db.commit()
