from __future__ import annotations

import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
import plotly.graph_objects as go
import plotly.utils as pu
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.database import models as m
from app.database import repositories as repo
from app.database.database import get_db
from app.services.notification_service import unread_count
from app.services import tools
from app.templating import templates

router = APIRouter()


@router.get("/desks")
def desks_page(
    request: Request,
    floor: str | None = None,
    team: str | None = None,
    space_type: str | None = None,
    availability: str | None = None,
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rooms = repo.list_rooms(db)
    users = db.query(m.User).all()
    desks = repo.list_desks(db)

    # Collect team chair counts
    team_set = set([u.team for u in users if u.team]) | set([r.team_name for r in rooms if r.team_name and r.team_name != "Shared"])
    distinct_teams = sorted(list(team_set)) if team_set else ["General Team"]

    # Colors for team bars
    colors = [
        "linear-gradient(90deg, #34d399, #10b981)",
        "linear-gradient(90deg, #818cf8, #6366f1)",
        "linear-gradient(90deg, #fb7185, #f43f5e)",
        "linear-gradient(90deg, #a78bfa, #8b5cf6)",
        "linear-gradient(90deg, #38bdf8, #0ea5e9)",
        "linear-gradient(90deg, #f472b6, #ec4899)",
        "linear-gradient(90deg, #fde047, #f59e0b)",
        "linear-gradient(90deg, #67e8f9, #06b6d4)",
    ]

    team_inventory = []
    total_team_chairs = 0
    max_chairs_single = 1

    for idx, t_name in enumerate(distinct_teams):
        t_clean = t_name.replace(" Team", "")
        t_rooms = [r for r in rooms if r.team_name == t_name or r.team_name == t_clean]
        ch = sum(r.chair_inventory for r in t_rooms)
        if ch == 0:
            ch = sum(r.capacity for r in t_rooms) or 10
        total_team_chairs += ch
        max_chairs_single = max(max_chairs_single, ch)
        team_inventory.append({
            "name": t_clean,
            "chairs": ch,
            "color": colors[idx % len(colors)],
            "raw_chairs": ch,
        })

    # Add shared / conference
    conf_rooms = [r for r in rooms if "Conference" in r.room_name or r.team_name == "Shared"]
    conf_chairs = sum(r.chair_inventory for r in conf_rooms) or 6

    for item in team_inventory:
        item["pct"] = round((item["raw_chairs"] / max(1, max_chairs_single)) * 100, 1)

    total_chairs = sum(r.chair_inventory for r in rooms) + len(desks)
    if total_chairs == 0:
        total_chairs = sum(r.capacity for r in rooms) or 50

    # Donut Chart: Chair Availability Overview
    donut_fig = go.Figure(
        data=[
            go.Pie(
                labels=["Team Chairs", "Shared & Conference"],
                values=[max(1, total_chairs - conf_chairs), conf_chairs],
                hole=0.72,
                marker=dict(colors=["#7b6fe6", "#38bdf8"]),
                textinfo="none",
                hoverinfo="label+value+percent",
                sort=False,
            )
        ]
    )
    donut_fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=180,
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    donut_json = json.dumps(donut_fig, cls=pu.PlotlyJSONEncoder)

    # Floor-wise inventory
    all_floors = sorted(list(set([r.floor for r in rooms] + [u.floor_preference for u in users])))
    floor_inventory = []
    floor_colors = ["#818cf8", "#38bdf8", "#34D399", "#FB923C", "#A78BFA"]
    floor_thumbs = ["/static/img/floor_thumb_gf.jpg", "/static/img/floor_thumb_3rd.jpg", "/static/img/floor_thumb_6th.jpg"]

    for idx, fl in enumerate(all_floors):
        fl_rooms = [r for r in rooms if r.floor == fl]
        fl_chairs = sum(r.chair_inventory for r in fl_rooms) or sum(r.capacity for r in fl_rooms) or 20
        fl_teams = list(set([r.team_name for r in fl_rooms if r.team_name]))
        fl_name = f"Floor {fl}" if fl > 0 else "Ground Floor"
        if fl == 3:
            fl_name = "3rd Floor"
        elif fl == 6:
            fl_name = "6th Floor"

        floor_inventory.append({
            "floor_name": fl_name,
            "team_name": ", ".join(fl_teams[:2]) if fl_teams else "Workplace Area",
            "desc": ", ".join(fl_teams) if len(fl_teams) > 2 else "",
            "chairs": fl_chairs,
            "pct": min(100, round((fl_chairs / max(1, total_chairs)) * 100)),
            "color": floor_colors[idx % len(floor_colors)],
            "thumb": floor_thumbs[idx % len(floor_thumbs)],
        })

    # Bench & Zone Utilization rows
    bench_zones = []
    for r in rooms:
        if "Hall" in r.room_name or r.bench_count > 0:
            bench_zones.append({
                "name": r.room_name,
                "type": r.room_type or "Hall",
                "capacity": f"{r.capacity} seats ({r.chair_inventory} chairs)",
                "status": "Awaiting live sensor data" if r.chair_inventory >= r.capacity else "Chair Gap Detected"
            })
    if not bench_zones:
        for r in rooms[:4]:
            bench_zones.append({
                "name": r.room_name,
                "type": r.room_type or "Space",
                "capacity": f"{r.capacity} seats",
                "status": "Active and operational"
            })

    # Seating Insights
    seating_pressure_areas = len([r for r in rooms if r.chair_inventory < r.capacity])
    seating_insights = []
    for r in rooms[:4]:
        if r.chair_inventory < r.capacity:
            seating_insights.append({
                "type": "alert",
                "icon": "!",
                "icon_class": "red",
                "title": f"{r.room_name} Seating Pressure",
                "desc": f"Configured capacity is {r.capacity} with {r.chair_inventory} tracked chairs.",
                "badge": "Attention",
                "badge_class": "attention",
            })
        else:
            seating_insights.append({
                "type": "success",
                "icon": "🪑",
                "icon_class": "green",
                "title": f"{r.room_name} Adequate Capacity",
                "desc": f"{r.chair_inventory} chairs allocated for {r.team_name or 'teams'}.",
                "badge": "Healthy",
                "badge_class": "healthy",
            })

    return templates.TemplateResponse(
        "desks.html",
        {
            "request": request,
            "user": user,
            "team_chairs": total_team_chairs,
            "conf_chairs": conf_chairs,
            "total_chairs": total_chairs,
            "seating_pressure_areas": seating_pressure_areas,
            "donut_json": donut_json,
            "team_inventory": team_inventory,
            "floor_inventory": floor_inventory,
            "bench_zones": bench_zones,
            "seating_insights": seating_insights,
            "unread": unread_count(db, user.id),
        },
    )


@router.get("/api/desks")
def api_desks(db: Session = Depends(get_db)):
    return JSONResponse(tools.get_desk_inventory(db))
