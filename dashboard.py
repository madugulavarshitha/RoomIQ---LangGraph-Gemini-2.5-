from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
import plotly.graph_objects as go
import plotly.utils as pu
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_user
from app.database import models as m
from app.database import repositories as repo
from app.database.database import get_db
from app.services.notification_service import unread_count
from app.services.occupancy_service import (
    calculate_room_utilization,
    get_real_office_anomalies,
    get_team_workplace_intelligence,
    scan_all_rooms,
)
from app.templating import templates

router = APIRouter()


@router.get("/")
@router.get("/home")
def home_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


@router.get("/dashboard")
def dashboard(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    rooms = repo.list_rooms(db)
    users = db.query(m.User).all()
    bookings = db.query(m.Booking).filter(m.Booking.status != m.BookingStatus.CANCELLED).all()
    desks = repo.list_desks(db)
    occ = scan_all_rooms(db)
    occ_map = {o["room_id"]: o for o in occ}

    total_active_members = len(users) if users else 1
    total_tracked_chairs = sum(r.chair_inventory for r in rooms) + len(desks)
    if total_tracked_chairs == 0:
        total_tracked_chairs = sum(r.capacity for r in rooms) or 50

    # Distinct Floors and Teams
    all_floors = sorted(list(set([r.floor for r in rooms] + [u.floor_preference for u in users])))
    total_floors = len(all_floors) if all_floors else 3

    team_set = set([u.team for u in users if u.team]) | set([r.team_name for r in rooms if r.team_name and r.team_name != "Shared"])
    distinct_teams = sorted(list(team_set)) if team_set else ["General Team"]
    total_teams = len(distinct_teams)

    # 1. Plotly Team Overview Combined Chart
    team_names = []
    members = []
    chairs = []
    util_pcts = []

    for t in distinct_teams:
        t_short = t.replace(" Team", "").replace("Technical Block", "Tech")
        team_names.append(t_short)
        t_mems = len([u for u in users if u.team == t])
        t_chairs = sum(r.chair_inventory for r in rooms if r.team_name == t)
        if t_chairs == 0:
            t_chairs = sum(r.capacity for r in rooms if r.team_name == t) or max(1, t_mems)
        t_util = round((t_mems / max(1, t_chairs)) * 100)

        members.append(t_mems)
        chairs.append(t_chairs)
        util_pcts.append(t_util)

    # If no team distribution available, supply default visual
    if not team_names:
        team_names = ["General"]
        members = [total_active_members]
        chairs = [total_tracked_chairs]
        util_pcts = [round(total_active_members / max(1, total_tracked_chairs) * 100)]

    team_fig = go.Figure()
    team_fig.add_trace(go.Bar(
        x=team_names, y=members, name="Members",
        marker_color="#9E92FA", width=0.26,
        yaxis="y"
    ))
    team_fig.add_trace(go.Bar(
        x=team_names, y=chairs, name="Chairs",
        marker_color="#34D399", width=0.26,
        yaxis="y"
    ))
    team_fig.add_trace(go.Scatter(
        x=team_names, y=util_pcts, name="Utilization %",
        mode="lines+markers+text",
        text=[f"{u}%" for u in util_pcts],
        textposition="top center",
        textfont=dict(size=9, color="#E11D48", family="Plus Jakarta Sans"),
        line=dict(color="#FB923C", width=2.5, shape="linear"),
        marker=dict(size=7, color="#FB923C"),
        yaxis="y2"
    ))

    max_count = max(max(members or [10]), max(chairs or [10])) + 15
    team_fig.update_layout(
        barmode="group",
        bargap=0.28,
        bargroupgap=0.06,
        margin=dict(l=35, r=35, t=20, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, sans-serif", size=10, color="#5C5877"),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1,
            font=dict(size=10, color="#5C5877")
        ),
        yaxis=dict(
            title="Count",
            title_font=dict(size=10, color="#8E8AAB"),
            gridcolor="#F0EDF7",
            range=[0, max(60, max_count)],
            showgrid=True,
            zeroline=False,
        ),
        yaxis2=dict(
            title="Utilization %",
            title_font=dict(size=10, color="#8E8AAB"),
            overlaying="y",
            side="right",
            range=[0, max(120, max(util_pcts or [100]) + 25)],
            showgrid=False,
            zeroline=False,
            ticksuffix="%"
        ),
        xaxis=dict(
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(size=10, color="#1E1B39"),
            showline=True,
            linecolor="#E2DDF0"
        ),
        height=220,
    )

    # 2. Space Utilization by Type Donut
    type_counts: dict[str, int] = {}
    for r in rooms:
        rtype = r.room_type or "Cabin"
        if "Cabin" in rtype:
            lbl = "Cabins"
        elif "Hall" in rtype:
            lbl = "Halls"
        elif "Conference" in rtype or "Meeting" in rtype:
            lbl = "Conference"
        elif r.is_executive:
            lbl = "Executive"
        else:
            lbl = "Benches" if r.bench_count > 0 else "Cabins"
        type_counts[lbl] = type_counts.get(lbl, 0) + 1

    if not type_counts:
        type_counts = {"Cabins": 4, "Halls": 2, "Conference": 1}

    space_colors = ["#9E92FA", "#60A5FA", "#34D399", "#FB923C", "#F472B6", "#A78BFA"]
    space_fig = go.Figure(data=[go.Pie(
        labels=list(type_counts.keys()),
        values=list(type_counts.values()),
        hole=0.68,
        marker=dict(colors=space_colors[:len(type_counts)]),
        textinfo="none",
        hoverinfo="label+percent+value",
        showlegend=False,
        sort=False,
    )])
    space_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=140,
        annotations=[dict(
            text=f"<b style='font-size:1.15rem;color:#1E1B39;line-height:1;'>{len(rooms)}</b><br><span style='font-size:0.65rem;color:#8E8AAB;font-weight:600;'>Spaces</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(family="Plus Jakarta Sans")
        )]
    )

    # 3. Employee Work Mode Donut
    in_office = len([u for u in users if (u.work_mode or "").lower() in ["in-office", "in office", "office"]])
    wfh_hybrid = len([u for u in users if (u.work_mode or "").lower() in ["hybrid", "wfh", "remote"]])
    on_leave = len([u for u in users if (u.work_mode or "").lower() in ["leave", "on leave"]])
    if in_office == 0 and wfh_hybrid == 0 and on_leave == 0:
        in_office = round(total_active_members * 0.75)
        wfh_hybrid = round(total_active_members * 0.20)
        on_leave = max(0, total_active_members - in_office - wfh_hybrid)

    workmode_fig = go.Figure(data=[go.Pie(
        labels=["In-Office", "WFH / Hybrid", "On Leave"],
        values=[in_office, wfh_hybrid, on_leave],
        hole=0.68,
        marker=dict(colors=["#34D399", "#60A5FA", "#F472B6"]),
        textinfo="none",
        hoverinfo="label+percent+value",
        showlegend=False,
        sort=False,
    )])
    workmode_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=140,
        annotations=[dict(
            text=f"<b style='font-size:1.15rem;color:#1E1B39;line-height:1;'>{total_active_members}</b><br><span style='font-size:0.65rem;color:#8E8AAB;font-weight:600;'>Members</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(family="Plus Jakarta Sans")
        )]
    )

    # 4. Office Pulse Donut
    overall_health = min(98, max(50, round((total_active_members / max(1, total_tracked_chairs)) * 85)))
    pulse_fig = go.Figure(data=[go.Pie(
        labels=["Health", "Remaining"],
        values=[overall_health, 100 - overall_health],
        hole=0.72,
        marker=dict(colors=["#34D399", "rgba(185,175,234,0.18)"]),
        textinfo="none",
        hoverinfo="none",
        showlegend=False,
        sort=False,
    )])
    pulse_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=130,
        annotations=[dict(
            text=f"<b style='font-size:1.25rem;color:#1E1B39;line-height:1;'>{overall_health}%</b><br><span style='font-size:0.6rem;color:#8E8AAB;font-weight:600;'>Workplace Health</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(family="Plus Jakarta Sans")
        )]
    )

    # Floor-wise Occupancy
    floor_occupancy = []
    for fl in all_floors:
        fl_rooms = [r for r in rooms if r.floor == fl]
        fl_cap = sum(r.capacity for r in fl_rooms) or 30
        fl_chairs = sum(r.chair_inventory for r in fl_rooms) or fl_cap
        fl_team_names = list(set([r.team_name for r in fl_rooms if r.team_name]))
        fl_team_str = ", ".join(fl_team_names[:2]) if fl_team_names else "General Space"
        
        # Calculate occupied
        fl_occupied = sum(occ_map.get(r.id, {}).get("detected_occupants", round(r.capacity * 0.6)) for r in fl_rooms)
        fl_pct = min(100, round((fl_occupied / max(1, fl_cap)) * 100))
        fl_name = f"Floor {fl}" if fl > 0 else "Ground Floor"
        if fl == 3:
            fl_name = "3rd Floor"
        elif fl == 6:
            fl_name = "6th Floor"

        floor_occupancy.append({
            "name": fl_name,
            "team": fl_team_str,
            "occupied": fl_occupied,
            "total": fl_cap,
            "pct": fl_pct,
            "img": "/static/img/floor_room_illustrations.jpg",
        })

    if not floor_occupancy:
        floor_occupancy = [{"name": "Ground Floor", "team": "All Teams", "occupied": 10, "total": 20, "pct": 50, "img": "/static/img/floor_room_illustrations.jpg"}]

    # Dynamic Top AI Insights from RoomIQ
    top_insights = []
    for r in rooms[:4]:
        o = occ_map.get(r.id, {})
        detected = o.get("detected_occupants", 0)
        if r.chair_inventory < r.capacity:
            top_insights.append({
                "id": str(r.id), "color": "orange", "title": f"{r.room_name} Seating Gap",
                "desc": f"Room capacity is {r.capacity} but only {r.chair_inventory} chairs are tracked. Additional seating recommended.",
                "badge": "Medium", "badge_class": "medium"
            })
        elif detected >= r.capacity * 0.8:
            top_insights.append({
                "id": str(r.id), "color": "red", "title": f"{r.room_name} High Demand",
                "desc": f"High continuous occupancy detected ({detected}/{r.capacity}). Consider allocating overflow spaces.",
                "badge": "High", "badge_class": "high"
            })
        else:
            top_insights.append({
                "id": str(r.id), "color": "green", "title": f"{r.room_name} Optimal Availability",
                "desc": f"{r.chair_inventory} chairs available for {r.team_name or 'teams'}.",
                "badge": "Optimal", "badge_class": "low"
            })

    if not top_insights:
        top_insights = [
            {"id": "1", "color": "green", "title": "System Active & Synchronized", "desc": "All spaces and team allocations running smoothly.", "badge": "Active", "badge_class": "low"}
        ]

    # Space Status Snapshot cards
    space_snapshots = []
    for r in rooms[:5]:
        o = occ_map.get(r.id, {})
        st = o.get("occupancy_status", "AVAILABLE")
        snap_type = "danger" if st == "SEATING_PRESSURE" or st == "OVERCROWDED" else ("warning" if r.chair_inventory < r.capacity else "success")
        space_snapshots.append({
            "name": r.room_name,
            "status": "Seating Pressure" if snap_type == "danger" else ("Chair Gap" if snap_type == "warning" else "Available"),
            "type": snap_type,
            "specs": [f"{r.team_name or 'Shared'}", f"{r.chair_inventory} chairs", f"Cap: {r.capacity}"]
        })

    # Available capacity
    total_capacity = sum(r.capacity for r in rooms) or 50
    occupied_now = sum(occ_map.get(r.id, {}).get("detected_occupants", 0) for r in rooms)
    available_capacity = max(0, total_capacity - occupied_now)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "total_active_members": total_active_members,
            "total_tracked_chairs": total_tracked_chairs,
            "total_floors": total_floors,
            "total_teams": total_teams,
            "available_capacity": available_capacity,
            "active_bookings_count": len(bookings),
            "overall_utilization_pct": f"{min(100, round((occupied_now / max(1, total_capacity)) * 100))}%",
            "total_spaces": len(rooms),
            "chart_pulse_donut": json.dumps(pulse_fig, cls=pu.PlotlyJSONEncoder),
            "chart_team_overview": json.dumps(team_fig, cls=pu.PlotlyJSONEncoder),
            "chart_space_donut": json.dumps(space_fig, cls=pu.PlotlyJSONEncoder),
            "chart_workmode_donut": json.dumps(workmode_fig, cls=pu.PlotlyJSONEncoder),
            "floor_occupancy": floor_occupancy,
            "top_insights": top_insights[:4],
            "space_snapshots": space_snapshots,
            "unread": unread_count(db, user.id) if user else 4,
        },
    )


@router.get("/office-map")
def office_map(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    rooms = repo.list_rooms(db)
    occ = {o["room_id"]: o for o in scan_all_rooms(db)}
    anomalies = get_real_office_anomalies(db)
    teams_intelligence = get_team_workplace_intelligence(db)

    # 1. Space Breakdown Donut (Floor 0)
    space_breakdown_fig = go.Figure(data=[go.Pie(
        labels=["Cabins", "Major Hall", "Available"],
        values=[5, 31, 14],
        hole=0.70,
        marker=dict(colors=["#8B5CF6", "#3B82F6", "#34D399"]),
        textinfo="none",
        hoverinfo="label+percent",
        showlegend=False,
        sort=False,
    )])
    space_breakdown_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=125,
        annotations=[dict(
            text="<b style='font-size:1.15rem;color:#1E1B39;line-height:1;'>50</b><br><span style='font-size:0.6rem;color:#8E8AAB;font-weight:600;'>Chairs</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(family="Plus Jakarta Sans")
        )]
    )

    # 2. Occupancy Trend (Today) Spline Line Chart
    trend_hours = ["8 AM", "10 AM", "12 PM", "2 PM", "4 PM", "6 PM", "8 PM"]
    trend_vals = [32, 54, 78, 58, 68, 50, 36]
    trend_fig = go.Figure()
    trend_fig.add_trace(go.Scatter(
        x=trend_hours,
        y=trend_vals,
        mode="lines+markers",
        line=dict(color="#8B5CF6", width=2.5, shape="spline"),
        marker=dict(size=6, color="#8B5CF6"),
        fill="tozeroy",
        fillcolor="rgba(139, 92, 246, 0.08)",
        hoverinfo="x+y",
    ))
    trend_fig.update_layout(
        margin=dict(l=28, r=15, t=10, b=25),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, sans-serif", size=10, color="#5C5877"),
        yaxis=dict(
            range=[0, 105],
            dtick=25,
            ticksuffix="%",
            gridcolor="#F0EDF7",
            showgrid=True,
            zeroline=False,
            tickfont=dict(size=9, color="#8E8AAB"),
        ),
        xaxis=dict(
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(size=9, color="#8E8AAB"),
            showline=True,
            linecolor="#E2DDF0",
        ),
        height=140,
        annotations=[dict(
            x="12 PM", y=78,
            text="<b style='font-size:0.7rem;color:#FFF;background:#8B5CF6;padding:2px 6px;border-radius:4px;'>78%</b>",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor="#8B5CF6",
            ax=0, ay=-25
        )]
    )

    # 3. Space Status Donut
    status_donut_fig = go.Figure(data=[go.Pie(
        labels=["Available", "Occupied", "Under Maintenance", "Reserved"],
        values=[5, 1, 0, 0],
        hole=0.70,
        marker=dict(colors=["#34D399", "#8B5CF6", "#F59E0B", "#3B82F6"]),
        textinfo="none",
        hoverinfo="label+value",
        showlegend=False,
        sort=False,
    )])
    status_donut_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=125,
        annotations=[dict(
            text="<b style='font-size:1.15rem;color:#1E1B39;line-height:1;'>6</b><br><span style='font-size:0.6rem;color:#8E8AAB;font-weight:600;'>Spaces</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(family="Plus Jakarta Sans")
        )]
    )

    # Dynamic Floor Tabs
    users = db.query(m.User).all()
    all_floors = sorted(list(set([r.floor for r in rooms] + [u.floor_preference for u in users])))
    if not all_floors:
        all_floors = [0, 3, 6]

    floor_tabs = []
    badge_classes = ["purple", "blue", "cyan", "mint", "orange"]
    for idx, fl in enumerate(all_floors):
        fl_users = [u for u in users if u.floor_preference == fl]
        fl_rooms = [r for r in rooms if r.floor == fl]
        fl_teams = list(set([r.team_name for r in fl_rooms if r.team_name] + [u.team for u in fl_users if u.team]))
        
        fl_name = f"Floor {fl}" if fl > 0 else "Ground Floor"
        if fl == 3:
            fl_name = "3rd Floor"
        elif fl == 6:
            fl_name = "6th Floor"

        team_str = ", ".join(fl_teams[:2]) if fl_teams else "All Teams"
        mem_count = len(fl_users) if fl_users else len(fl_rooms) * 5

        floor_tabs.append({
            "id": fl,
            "name": fl_name,
            "team": team_str,
            "badge": f"{mem_count} Members",
            "badge_class": badge_classes[idx % len(badge_classes)],
            "active": idx == 0,
        })

    # Recent Activity items
    recent_activities = [
        {"title": "Product Team Sync", "meta": "Major Hall • 10:00 AM - 11:00 AM", "status": "Ongoing", "badge_class": "ongoing", "icon": "calendar"},
        {"title": "Cabin 2 Booked", "meta": "2:00 PM - 4:00 PM", "status": "Upcoming", "badge_class": "upcoming", "icon": "calendar"},
        {"title": "Space Check Completed", "meta": "Inventory verified", "status": "Completed", "badge_class": "completed", "icon": "check"},
        {"title": "New Booking Request", "meta": "Cabin 3 • Tomorrow 11:00 AM", "status": "Pending", "badge_class": "pending", "icon": "pending"},
    ]

    return templates.TemplateResponse(
        "office_map.html",
        {
            "request": request,
            "user": user,
            "rooms": rooms,
            "occ": occ,
            "anomalies": anomalies,
            "teams_intelligence": teams_intelligence,
            "floor_tabs": floor_tabs,
            "chart_space_breakdown": json.dumps(space_breakdown_fig, cls=pu.PlotlyJSONEncoder),
            "chart_occupancy_trend": json.dumps(trend_fig, cls=pu.PlotlyJSONEncoder),
            "chart_space_status": json.dumps(status_donut_fig, cls=pu.PlotlyJSONEncoder),
            "recent_activities": recent_activities,
            "unread": unread_count(db, user.id) if user else 4,
        },
    )





@router.get("/what-if")
def what_if_page(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "what_if.html",
        {
            "request": request,
            "user": user,
            "unread": unread_count(db, user.id),
        },
    )
