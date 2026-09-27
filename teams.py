from __future__ import annotations

import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_user
from app.database import models as m
from app.database.database import get_db
from app.services.notification_service import unread_count
from app.templating import templates

router = APIRouter()

# Metadata matching the exact UI design in the reference
TEAMS_CONFIG = [
    {
        "id": "product",
        "name": "Product Team",
        "team_key": "Product",
        "floor": "Ground Floor",
        "floor_num": 0,
        "members": 35,
        "chairs": 65,
        "avatar_plus": "+30",
        "icon": "cube",
        "icon_bg": "#EDE9FE",
        "icon_color": "#7C3AED",
        "badge_color": "purple",
    },
    {
        "id": "operations",
        "name": "Operations Team",
        "team_key": "Operations",
        "floor": "3rd Floor",
        "floor_num": 3,
        "members": 75,
        "chairs": 98,
        "avatar_plus": "+70",
        "icon": "gear",
        "icon_bg": "#FFEDD5",
        "icon_color": "#EA580C",
        "badge_color": "orange",
    },
    {
        "id": "fsd",
        "name": "FSD Team",
        "team_key": "FSD",
        "floor": "6th Floor",
        "floor_num": 6,
        "members": 15,
        "chairs": 10,
        "avatar_plus": "+10",
        "icon": "chip",
        "icon_bg": "#FFE4E6",
        "icon_color": "#E11D48",
        "badge_color": "pink",
    },
    {
        "id": "servicenow",
        "name": "ServiceNow Team",
        "team_key": "ServiceNow",
        "floor": "6th Floor",
        "floor_num": 6,
        "members": 38,
        "chairs": 56,
        "avatar_plus": "+33",
        "icon": "cloud-blue",
        "icon_bg": "#E0F2FE",
        "icon_color": "#0284C7",
        "badge_color": "blue",
    },
    {
        "id": "salesforce",
        "name": "Salesforce Team",
        "team_key": "Salesforce",
        "floor": "6th Floor",
        "floor_num": 6,
        "members": 9,
        "chairs": 32,
        "avatar_plus": "+4",
        "icon": "cloud-green",
        "icon_bg": "#DCFCE7",
        "icon_color": "#16A34A",
        "badge_color": "green",
    },
    {
        "id": "aitech",
        "name": "AI / Technical Team",
        "team_key": "AI / Technical",
        "floor": "6th Floor",
        "floor_num": 6,
        "members": 29,
        "chairs": 46,
        "avatar_plus": "+24",
        "icon": "brain",
        "icon_bg": "#F3E8FF",
        "icon_color": "#9333EA",
        "badge_color": "purple",
    },
    {
        "id": "marketing",
        "name": "Marketing Team",
        "team_key": "Marketing",
        "floor": "6th Floor",
        "floor_num": 6,
        "members": 9,
        "chairs": 19,
        "avatar_plus": "+4",
        "icon": "speaker",
        "icon_bg": "#FCE7F3",
        "icon_color": "#DB2777",
        "badge_color": "pink",
    },
]

# Seeded representative members matching the visual prototype
MEMBER_SEED_DATA = [
    {
        "name": "Aarav Sharma",
        "email": "aarav.sharma@company.com",
        "initials": "AS",
        "avatar_color": "#34D399",  # Green
        "team": "Product",
        "team_class": "badge-product",
        "role": "Product Manager",
        "floor": "Ground Floor",
        "floor_num": 0,
        "workspace": "Cabin 1",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Priya Jadhav",
        "email": "priya.jadhav@company.com",
        "initials": "PJ",
        "avatar_color": "#FB7185",  # Coral / Pink
        "team": "Operations",
        "team_class": "badge-operations",
        "role": "Operations Lead",
        "floor": "3rd Floor",
        "floor_num": 3,
        "workspace": "Cabin 2",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Rohit Kumar",
        "email": "rohit.kumar@company.com",
        "initials": "RK",
        "avatar_color": "#60A5FA",  # Blue
        "team": "FSD",
        "team_class": "badge-fsd",
        "role": "Developer",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "FSD Room",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Sneha Nair",
        "email": "sneha.nair@company.com",
        "initials": "SN",
        "avatar_color": "#38BDF8",  # Cyan
        "team": "ServiceNow",
        "team_class": "badge-servicenow",
        "role": "Tech Lead",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Cabin 1",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Vikram T",
        "email": "vikram.t@company.com",
        "initials": "VT",
        "avatar_color": "#FB923C",  # Orange
        "team": "Salesforce",
        "team_class": "badge-salesforce",
        "role": "Developer",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Salesforce Hall",
        "status": "On Leave",
        "status_class": "status-leave",
    },
    {
        "name": "Ananya Iyer",
        "email": "ananya.iyer@company.com",
        "initials": "AI",
        "avatar_color": "#A78BFA",  # Violet
        "team": "AI / Technical",
        "team_class": "badge-aitech",
        "role": "AI Engineer",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Cabin 2",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Rohan Mehta",
        "email": "rohan.mehta@company.com",
        "initials": "RM",
        "avatar_color": "#F472B6",  # Pink
        "team": "Marketing",
        "team_class": "badge-marketing",
        "role": "Growth Lead",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Cabin 3",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Ava Sharma",
        "email": "ava.sharma@company.com",
        "initials": "AS",
        "avatar_color": "#9333EA",
        "team": "Operations",
        "team_class": "badge-operations",
        "role": "Director of Operations",
        "floor": "3rd Floor",
        "floor_num": 3,
        "workspace": "Executive Cabin",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Marcus Lee",
        "email": "marcus.lee@company.com",
        "initials": "ML",
        "avatar_color": "#10B981",
        "team": "Operations",
        "team_class": "badge-operations",
        "role": "Facilities Lead",
        "floor": "3rd Floor",
        "floor_num": 3,
        "workspace": "Operations Hall",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Jordan Blake",
        "email": "jordan.blake@company.com",
        "initials": "JB",
        "avatar_color": "#6366F1",
        "team": "Product",
        "team_class": "badge-product",
        "role": "Lead Designer",
        "floor": "Ground Floor",
        "floor_num": 0,
        "workspace": "Major Hall",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Nikhil Gupta",
        "email": "nikhil.gupta@company.com",
        "initials": "NG",
        "avatar_color": "#EC4899",
        "team": "FSD",
        "team_class": "badge-fsd",
        "role": "Full Stack Engineer",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "FSD Room",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Meera Patel",
        "email": "meera.patel@company.com",
        "initials": "MP",
        "avatar_color": "#06B6D4",
        "team": "ServiceNow",
        "team_class": "badge-servicenow",
        "role": "System Architect",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Cabin 1",
        "status": "Hybrid",
        "status_class": "status-hybrid",
    },
    {
        "name": "Karthik R",
        "email": "karthik.r@company.com",
        "initials": "KR",
        "avatar_color": "#22C55E",
        "team": "Salesforce",
        "team_class": "badge-salesforce",
        "role": "CRM Specialist",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Salesforce Hall",
        "status": "Active",
        "status_class": "status-active",
    },
    {
        "name": "Divya S",
        "email": "divya.s@company.com",
        "initials": "DS",
        "avatar_color": "#8B5CF6",
        "team": "AI / Technical",
        "team_class": "badge-aitech",
        "role": "ML Engineer",
        "floor": "6th Floor",
        "floor_num": 6,
        "workspace": "Cabin 2",
        "status": "Active",
        "status_class": "status-active",
    },
]


@router.get("/teams")
def teams_directory(
    request: Request,
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    users = db.query(m.User).order_by(m.User.team, m.User.full_name).all()
    rooms = db.query(m.Room).all()

    # Collect distinct teams
    team_set = set([u.team for u in users if u.team]) | set([r.team_name for r in rooms if r.team_name and r.team_name != "Shared"])
    distinct_teams = sorted(list(team_set)) if team_set else ["General Team"]

    # Visual presets for teams
    team_style_presets = {
        "Product": {"icon": "cube", "icon_bg": "#EDE9FE", "icon_color": "#7C3AED", "badge_color": "purple", "class": "badge-product"},
        "Operations": {"icon": "gear", "icon_bg": "#FFEDD5", "icon_color": "#EA580C", "badge_color": "orange", "class": "badge-operations"},
        "FSD": {"icon": "chip", "icon_bg": "#FFE4E6", "icon_color": "#E11D48", "badge_color": "pink", "class": "badge-fsd"},
        "ServiceNow": {"icon": "cloud-blue", "icon_bg": "#E0F2FE", "icon_color": "#0284C7", "badge_color": "blue", "class": "badge-servicenow"},
        "Salesforce": {"icon": "cloud-green", "icon_bg": "#DCFCE7", "icon_color": "#16A34A", "badge_color": "green", "class": "badge-salesforce"},
        "AI / Technical": {"icon": "brain", "icon_bg": "#F3E8FF", "icon_color": "#9333EA", "badge_color": "purple", "class": "badge-aitech"},
        "AI": {"icon": "brain", "icon_bg": "#F3E8FF", "icon_color": "#9333EA", "badge_color": "purple", "class": "badge-aitech"},
        "Marketing": {"icon": "speaker", "icon_bg": "#FCE7F3", "icon_color": "#DB2777", "badge_color": "pink", "class": "badge-marketing"},
        "Leadership": {"icon": "cube", "icon_bg": "#EDE9FE", "icon_color": "#7C3AED", "badge_color": "purple", "class": "badge-product"},
        "Engineering": {"icon": "chip", "icon_bg": "#FFE4E6", "icon_color": "#E11D48", "badge_color": "pink", "class": "badge-fsd"},
        "Sales": {"icon": "cloud-green", "icon_bg": "#DCFCE7", "icon_color": "#16A34A", "badge_color": "green", "class": "badge-salesforce"},
    }

    dynamic_teams = []
    for t_name in distinct_teams:
        t_short = t_name.replace(" Team", "").strip()
        t_users = [u for u in users if u.team == t_name or u.team == t_short]
        t_rooms = [r for r in rooms if r.team_name == t_name or r.team_name == t_short]
        
        t_chairs = sum(r.chair_inventory for r in t_rooms)
        if t_chairs == 0:
            t_chairs = sum(r.capacity for r in t_rooms) or max(1, len(t_users))
            
        floor_num = t_rooms[0].floor if t_rooms else (t_users[0].floor_preference if t_users else 0)
        floor_lbl = f"Floor {floor_num}" if floor_num > 0 else "Ground Floor"
        if floor_num == 3:
            floor_lbl = "3rd Floor"
        elif floor_num == 6:
            floor_lbl = "6th Floor"

        style = team_style_presets.get(t_short, {
            "icon": "cube", "icon_bg": "#EDE9FE", "icon_color": "#7C3AED", "badge_color": "purple", "class": "badge-product"
        })

        plus_count = f"+{max(0, len(t_users) - 5)}" if len(t_users) > 5 else f"+{len(t_users)}"

        dynamic_teams.append({
            "id": t_short.lower().replace(" ", "_").replace("/", ""),
            "name": t_name if "Team" in t_name else f"{t_name} Team",
            "team_key": t_short,
            "floor": floor_lbl,
            "floor_num": floor_num,
            "members": len(t_users),
            "chairs": t_chairs,
            "avatar_plus": plus_count,
            "icon": style["icon"],
            "icon_bg": style["icon_bg"],
            "icon_color": style["icon_color"],
            "badge_color": style["badge_color"],
        })

    # Map members
    avatar_palette = ["#34D399", "#FB7185", "#60A5FA", "#38BDF8", "#FB923C", "#A78BFA", "#F472B6", "#9333EA", "#10B981"]
    dynamic_members = []
    
    for idx, u in enumerate(users):
        initials = "".join([p[0].upper() for p in u.full_name.strip().split() if p])[:2] or "EM"
        color = avatar_palette[idx % len(avatar_palette)]
        t_clean = (u.team or "General").replace(" Team", "")
        style = team_style_presets.get(t_clean, {"class": "badge-product"})
        
        fl_num = u.floor_preference or 0
        fl_str = f"Floor {fl_num}" if fl_num > 0 else "Ground Floor"
        if fl_num == 3:
            fl_str = "3rd Floor"
        elif fl_num == 6:
            fl_str = "6th Floor"

        st = "Active"
        st_class = "status-active"
        if (u.work_mode or "").lower() in ["leave", "on leave"]:
            st = "On Leave"
            st_class = "status-leave"
        elif (u.work_mode or "").lower() in ["hybrid", "wfh", "remote"]:
            st = "Hybrid"
            st_class = "status-hybrid"

        dynamic_members.append({
            "name": u.full_name,
            "email": u.email,
            "initials": initials,
            "avatar_color": color,
            "team": t_clean,
            "team_class": style.get("class", "badge-product"),
            "role": u.department or u.role.value if hasattr(u.role, 'value') else "Member",
            "floor": fl_str,
            "floor_num": fl_num,
            "workspace": f"Floor {fl_num} Area",
            "status": st,
            "status_class": st_class,
        })

    total_chairs = sum(r.chair_inventory for r in rooms) or 267
    all_floors = sorted(list(set([r.floor for r in rooms] + [u.floor_preference for u in users])))

    return templates.TemplateResponse(
        "teams.html",
        {
            "request": request,
            "user": user,
            "total_members": len(users),
            "total_chairs": total_chairs,
            "total_teams": len(dynamic_teams),
            "total_floors": len(all_floors) if all_floors else 3,
            "teams": dynamic_teams,
            "members": dynamic_members,
            "unread": unread_count(db, user.id) if user else 4,
        },
    )


@router.post("/api/teams/members")
def add_team_member(
    name: str = Form(...),
    email: str = Form(...),
    team: str = Form(...),
    role: str = Form(...),
    floor: str = Form(...),
    workspace: str = Form(...),
    status: str = Form("Active"),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    from app.auth.security import hash_password
    
    # Check if user already exists
    existing = db.query(m.User).filter(m.User.email == email.lower().strip()).first()
    fl_num = 0
    if "3" in floor:
        fl_num = 3
    elif "6" in floor:
        fl_num = 6
    elif "1" in floor:
        fl_num = 1
    elif "2" in floor:
        fl_num = 2

    if not existing:
        new_user = m.User(
            full_name=name.strip(),
            email=email.lower().strip(),
            password_hash=hash_password("Password123!"),
            role=m.Role.EMPLOYEE,
            department=role.strip(),
            team=team.strip(),
            work_mode=status.strip(),
            floor_preference=fl_num,
        )
        db.add(new_user)
        db.commit()

    initials = "".join([part[0].upper() for part in name.strip().split() if part])[:2] or "EM"
    
    team_classes = {
        "Product": "badge-product",
        "Operations": "badge-operations",
        "FSD": "badge-fsd",
        "ServiceNow": "badge-servicenow",
        "Salesforce": "badge-salesforce",
        "AI / Technical": "badge-aitech",
        "Marketing": "badge-marketing",
    }
    
    status_classes = {
        "Active": "status-active",
        "On Leave": "status-leave",
        "Hybrid": "status-hybrid",
    }
    
    avatar_colors = ["#34D399", "#FB7185", "#60A5FA", "#38BDF8", "#FB923C", "#A78BFA", "#F472B6", "#9333EA", "#10B981"]
    import random
    color = random.choice(avatar_colors)

    new_member = {
        "name": name,
        "email": email,
        "initials": initials,
        "avatar_color": color,
        "team": team,
        "team_class": team_classes.get(team, "badge-product"),
        "role": role,
        "floor": floor,
        "workspace": workspace,
        "status": status,
        "status_class": status_classes.get(status, "status-active"),
    }
    
    return JSONResponse(status_code=200, content={"success": True, "member": new_member})
