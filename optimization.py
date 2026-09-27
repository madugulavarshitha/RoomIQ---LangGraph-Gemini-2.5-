from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import require_manager_or_admin, require_user
from app.database import models as m
from app.database.database import get_db
from app.graph.workflow import run_optimization_workflow
from app.services import tools
from app.services.notification_service import unread_count
from app.templating import templates

router = APIRouter()

AGENT_PIPELINE = [
    ("Space Coordinator Agent", "Supervises the entire optimization workflow and produces the final result."),
    ("Demand Prediction Agent", "Forecasts room and desk demand from historical bookings using Pandas + Scikit-learn."),
    ("Occupancy Monitoring Agent", "Compares booked status with live sensor occupancy to detect underutilized rooms."),
    ("Space Reallocation Agent", "Matches underused rooms to waiting meeting and desk requests."),
    ("Booking & Scheduling Agent", "Applies reallocations, updates reservations, and resolves conflicts."),
    ("Notification Agent", "Notifies affected employees and facilities staff of every change."),
    ("Utilization Analytics Agent", "Records utilization metrics and generates insights for future predictions."),
]


@router.get("/optimization")
def optimization_center(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    latest_run = db.query(m.AgentRun).order_by(m.AgentRun.started_at.desc()).first()
    events = []
    if latest_run:
        events = (
            db.query(m.AgentEvent)
            .filter(m.AgentEvent.run_id == latest_run.id)
            .order_by(m.AgentEvent.created_at)
            .all()
        )
    events_by_agent = {e.agent_name: e for e in events}

    return templates.TemplateResponse(
        "optimization.html",
        {
            "request": request,
            "user": user,
            "pipeline": AGENT_PIPELINE,
            "latest_run": latest_run,
            "events_by_agent": events_by_agent,
            "can_run": user.role in (m.Role.FACILITIES_MANAGER, m.Role.ADMIN),
            "unread": unread_count(db, user.id),
        },
    )


@router.post("/api/optimization/run")
def run_optimization(user: m.User = Depends(require_manager_or_admin), db: Session = Depends(get_db)):
    state = run_optimization_workflow(db, "Optimize Monday workplace allocation", triggered_by=user.id)
    run = db.get(m.AgentRun, state["run_id"])
    return JSONResponse(
        {
            "run_id": state["run_id"],
            "final_decision": state.get("final_decision"),
            "agent_status": state.get("agent_status", {}),
            "recommendations": state.get("recommendations", []),
            "reallocations": state.get("reallocations", []),
            "notifications_sent": len(state.get("notifications", [])),
            "analytics": state.get("analytics", {}),
            "metrics": {
                "rooms_reallocated": run.rooms_reallocated if run else 0,
                "desk_requests_resolved": run.desk_requests_resolved if run else 0,
                "conflicts_resolved": run.conflicts_resolved if run else 0,
                "unused_capacity_reduced_pct": run.unused_capacity_reduced_pct if run else 0,
                "notifications_sent": run.notifications_sent if run else 0,
            },
        }
    )


@router.get("/agents")
def agent_center(request: Request, user: m.User = Depends(require_user), db: Session = Depends(get_db)):
    agent_stats = []
    for name, purpose in AGENT_PIPELINE:
        events = db.query(m.AgentEvent).filter(m.AgentEvent.agent_name == name).order_by(m.AgentEvent.created_at.desc()).all()
        count = len(events)
        success = len([e for e in events if e.status == "COMPLETED"])
        avg_time = round(sum(e.duration_ms for e in events) / count, 1) if count else 0.0
        last = events[0] if events else None
        agent_stats.append(
            {
                "name": name,
                "purpose": purpose,
                "status": last.status if last else "IDLE",
                "last_execution": last.created_at if last else None,
                "execution_count": count,
                "success_rate": round(success / count * 100, 1) if count else 0.0,
                "avg_duration_ms": avg_time,
                "current_task": last.action if last and last.status == "RUNNING" else (last.action if last else "Awaiting next optimization run"),
            }
        )

    timeline = db.query(m.AgentEvent).order_by(m.AgentEvent.created_at.desc()).limit(30).all()

    return templates.TemplateResponse(
        "agents.html",
        {"request": request, "user": user, "agent_stats": agent_stats, "timeline": timeline, "unread": unread_count(db, user.id)},
    )


@router.get("/reallocation")
def reallocation_center(request: Request, user: m.User = Depends(require_manager_or_admin), db: Session = Depends(get_db)):
    opportunities = (
        db.query(m.ReallocationEvent)
        .filter(m.ReallocationEvent.status == "RECOMMENDED")
        .order_by(m.ReallocationEvent.created_at.desc())
        .all()
    )
    applied = (
        db.query(m.ReallocationEvent)
        .filter(m.ReallocationEvent.status == "APPLIED")
        .order_by(m.ReallocationEvent.created_at.desc())
        .limit(10)
        .all()
    )
    room_names = {r.id: r.room_name for r in db.query(m.Room).all()}
    return templates.TemplateResponse(
        "reallocation.html",
        {
            "request": request,
            "user": user,
            "opportunities": opportunities,
            "applied": applied,
            "room_names": room_names,
            "unread": unread_count(db, user.id),
        },
    )


@router.post("/api/reallocation/{event_id}/apply")
def apply_reallocation(event_id: str, user: m.User = Depends(require_manager_or_admin), db: Session = Depends(get_db)):
    event = db.get(m.ReallocationEvent, event_id)
    if event is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    event.status = "APPLIED"
    db.commit()
    return RedirectResponse("/reallocation", status_code=303)


@router.post("/api/reallocation/{event_id}/reject")
def reject_reallocation(event_id: str, user: m.User = Depends(require_manager_or_admin), db: Session = Depends(get_db)):
    event = db.get(m.ReallocationEvent, event_id)
    if event is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    event.status = "REJECTED"
    db.commit()
    return RedirectResponse("/reallocation", status_code=303)


@router.get("/audit")
def audit_log(request: Request, user: m.User = Depends(require_manager_or_admin), db: Session = Depends(get_db)):
    logs = db.query(m.AuditLog).order_by(m.AuditLog.timestamp.desc()).limit(100).all()
    return templates.TemplateResponse("audit.html", {"request": request, "user": user, "logs": logs, "unread": unread_count(db, user.id)})
