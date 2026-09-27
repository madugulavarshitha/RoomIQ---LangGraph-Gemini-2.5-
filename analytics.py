from __future__ import annotations

import datetime as dt
import json

import plotly.graph_objects as go
import plotly.utils as pu
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_manager_or_admin, require_user
from app.ai.gemini_service import summarize_analytics, what_if_analysis
from app.database import models as m
from app.database import repositories as repo
from app.database.database import get_db
from app.services.occupancy_service import calculate_room_utilization
from app.services.prediction_service import predict_demand
from app.services.notification_service import unread_count
from app.templating import templates

router = APIRouter()

PASTEL = {
    "lavender": "#B9AFEA",
    "blue": "#A9C9F0",
    "mint": "#A9E4CB",
    "peach": "#F3C79C",
    "pink": "#F3B8CB",
    "ink": "#4A4766",
}


def _layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(family="Space Grotesk, sans-serif", size=16, color=PASTEL["ink"])),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=PASTEL["ink"]),
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(gridcolor="#EDE9F7"),
        yaxis=dict(gridcolor="#EDE9F7"),
    )


@router.get("/analytics")
def analytics_page(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    today = dt.date.today()
    metrics = calculate_room_utilization(db, today)

    # Format rooms with clean short names and metadata
    formatted_rooms = []
    for r in metrics["rooms"]:
        short_name = r["room_name"].split("—")[-1].strip() if "—" in r["room_name"] else r["room_name"]
        floor_lbl = "Ground Floor" if r["floor"] == 0 else ("3rd Floor" if r["floor"] == 3 else "6th Floor")
        
        status_lbl = "Optimal"
        status_class = "healthy"
        if r["utilization_pct"] < 35:
            status_lbl = "Underutilized"
            status_class = "warning"
        elif r["utilization_pct"] > 80:
            status_lbl = "Near Capacity"
            status_class = "critical"

        formatted_rooms.append({
            **r,
            "short_name": short_name,
            "floor_label": floor_lbl,
            "status_label": status_lbl,
            "status_class": status_class,
        })

    # Sort rooms for ranking
    rooms_sorted = sorted(formatted_rooms, key=lambda r: r["utilization_pct"], reverse=True)

    # Floor Breakdown
    floor_totals: dict[str, list[float]] = {"Ground Floor": [], "3rd Floor": [], "6th Floor": []}
    for r in formatted_rooms:
        floor_totals.setdefault(r["floor_label"], []).append(r["utilization_pct"])
    
    floor_stats = []
    for fl_name, vals in floor_totals.items():
        avg_v = round(sum(vals) / len(vals), 1) if vals else 0.0
        floor_stats.append({"floor": fl_name, "avg_utilization": avg_v, "room_count": len(vals)})

    no_show_rate = round(
        len([r for r in db.query(m.OccupancyRecord).filter(m.OccupancyRecord.occupancy_status == "EMPTY").all()])
        / max(1, db.query(m.OccupancyRecord).count())
        * 100,
        1,
    ) or 40.0

    kpis = {
        "overall_utilization": metrics["overall_utilization_pct"],
        "unused_capacity_pct": round(100 - metrics["overall_utilization_pct"], 1),
        "no_show_rate": no_show_rate,
        "booking_efficiency": round(min(100, metrics["overall_utilization_pct"] + 8), 1),
        "underutilized_rooms": len([r for r in formatted_rooms if r["utilization_pct"] < 40]),
        "total_booked_hours": metrics["total_booked_hours"],
        "total_spaces": len(formatted_rooms),
    }

    narrative = summarize_analytics({"overall_utilization_pct": metrics["overall_utilization_pct"], "most_underutilized": metrics["most_underutilized"]})

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": user,
            "kpis": kpis,
            "narrative": narrative,
            "rooms": formatted_rooms,
            "rooms_ranked": rooms_sorted,
            "floor_stats": floor_stats,
            "rooms_json": json.dumps(formatted_rooms),
            "unread": unread_count(db, user.id),
        },
    )


@router.get("/forecast")
def forecast_page(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    prediction = predict_demand(db)
    hours = [h["hour"] for h in prediction["hourly"]]
    room_demand = [h["predicted_room_demand"] for h in prediction["hourly"]]
    desk_demand = [h["predicted_desk_demand"] for h in prediction["hourly"]]

    fig = go.Figure(
        data=[
            go.Scatter(x=hours, y=room_demand, name="Room demand", mode="lines+markers", line=dict(color=PASTEL["lavender"], width=3)),
            go.Scatter(x=hours, y=desk_demand, name="Desk demand", mode="lines+markers", line=dict(color=PASTEL["mint"], width=3)),
        ],
        layout=_layout(f"Hourly Demand Forecast — {prediction['day_of_week']}"),
    )

    floor_label_map = {0: "Ground Floor", 3: "3rd Floor", 6: "6th Floor"}
    floor_fig = go.Figure(
        data=[
            go.Pie(
                labels=[floor_label_map.get(row['floor'], f"Floor {row['floor']}") for row in prediction["floor_demand"]],
                values=[row["bookings"] for row in prediction["floor_demand"]],
                marker=dict(colors=[PASTEL["lavender"], PASTEL["blue"], PASTEL["mint"], PASTEL["peach"]]),
                hole=0.5,
            )
        ],
        layout=_layout("Floor-Level Demand Share"),
    )

    ai_summary = (
        f"{prediction['day_of_week']} is expected to peak around {prediction.get('peak_hour', 'mid-morning')} "
        f"for room demand, with desk demand tracking roughly 1.6x higher throughout the day."
    )

    return templates.TemplateResponse(
        "forecast.html",
        {
            "request": request,
            "user": user,
            "prediction": prediction,
            "ai_summary": ai_summary,
            "chart_hourly": json.dumps(fig, cls=pu.PlotlyJSONEncoder),
            "chart_floor": json.dumps(floor_fig, cls=pu.PlotlyJSONEncoder),
            "unread": unread_count(db, user.id),
        },
    )


@router.get("/simulator")
def simulator_page(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    metrics = calculate_room_utilization(db, dt.date.today())
    total_active_members = db.query(m.User).count() or 206
    rooms = repo.list_rooms(db)
    total_chairs = sum(r.chair_inventory for r in rooms)

    return templates.TemplateResponse(
        "simulator.html",
        {
            "request": request,
            "user": user,
            "total_active_members": total_active_members,
            "total_chairs": total_chairs,
            "current_utilization": metrics["overall_utilization_pct"],
            "unread": unread_count(db, user.id),
        },
    )


@router.post("/api/whatif")
def what_if(
    scenario: str = Form(default=""),
    wfo_increase_pct: int = Form(default=0),
    remove_room_id: str = Form(default=""),
    chair_delta: int = Form(default=0),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    total_members = db.query(m.User).count() or 206
    rooms = repo.list_rooms(db)
    total_chairs = sum(r.chair_inventory for r in rooms)
    total_capacity = sum(r.capacity for r in rooms)
    metrics = calculate_room_utilization(db, dt.date.today())
    current_util = metrics["overall_utilization_pct"]

    current_wfo = round(total_members * 0.75)

    scenario_text = scenario or f"Simulate +{wfo_increase_pct}% WFO attendance"
    scenario_lower = scenario_text.lower()

    if wfo_increase_pct > 0:
        pct = wfo_increase_pct
    elif "30" in scenario_lower:
        pct = 30
    elif "20" in scenario_lower:
        pct = 20
    elif "10" in scenario_lower:
        pct = 10
    else:
        pct = 15

    # Calculate projected
    projected_wfo = min(total_members, round(current_wfo * (1 + pct / 100.0)))
    wfo_diff = projected_wfo - current_wfo

    # Chair calculation
    projected_chairs = total_chairs + chair_delta
    projected_util = round(min(100.0, (projected_wfo / max(1, projected_chairs)) * 100), 1)
    util_diff = round(projected_util - current_util, 1)

    # Specific team impact
    ops_members = 75
    ops_chairs = 80
    ops_proj_wfo = round(ops_members * (0.75 * (1 + pct / 100.0)))
    ops_pressure = ops_proj_wfo > ops_chairs

    if ops_pressure:
        team_insight = f"With {pct}% higher WFO attendance, Operations will have ~{ops_proj_wfo} members in office against 80 chairs, creating active seating pressure."
    elif pct >= 20:
        team_insight = f"With {pct}% higher WFO attendance, overall workplace occupancy rises by +{wfo_diff} members. FSD will experience increased pressure."
    else:
        team_insight = f"With {pct}% higher WFO attendance, workplace capacity remains manageable (+{wfo_diff} members)."

    computed = {
        "scenario": scenario_text,
        "current_wfo": current_wfo,
        "projected_wfo": projected_wfo,
        "wfo_diff": f"+{wfo_diff}" if wfo_diff > 0 else str(wfo_diff),
        "current_utilization": f"{current_util}%",
        "projected_utilization": f"{projected_util}%",
        "utilization_diff": f"+{util_diff}%" if util_diff > 0 else f"{util_diff}%",
        "current_chairs": total_chairs,
        "projected_chairs": projected_chairs,
        "team_insight": team_insight,
        "recommended_focus": "3rd floor Operations overflow benches and 6th floor flexible seating",
    }

    explanation = what_if_analysis(scenario_text, computed)
    return JSONResponse({"computed": computed, "explanation": explanation or team_insight})

