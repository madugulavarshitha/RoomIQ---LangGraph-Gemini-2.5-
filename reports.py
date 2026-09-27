from __future__ import annotations

import csv
import datetime as dt
import io
import json

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.agents.meeting_intelligence_agent import run_meeting_audit
from app.auth.deps import require_user
from app.database import models as m
from app.database.database import get_db
from app.services.notification_service import unread_count
from app.services.reports_service import get_meeting_intelligence_report
from app.templating import templates

router = APIRouter()


@router.get("/reports")
def reports_page(
    request: Request,
    period: str = Query("monthly"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    floor: int | None = Query(None),
    team: str | None = Query(None),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    report_data = run_meeting_audit(
        db,
        period=period,
        custom_start=start_date,
        custom_end=end_date,
        floor_filter=floor,
        team_filter=team,
    )

    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "user": user,
            "period": period,
            "period_label": report_data["period_label"],
            "start_date": report_data["start_date"],
            "end_date": report_data["end_date"],
            "selected_floor": floor,
            "selected_team": team or "ALL",
            "summary": report_data["summary"],
            "floor_breakdown": report_data["floor_breakdown"],
            "team_breakdown": report_data["team_breakdown"],
            "meetings": report_data["meetings"],
            "meetings_json": json.dumps(report_data["meetings"]),
            "room_spatial_3d_json": report_data["room_spatial_3d_json"],
            "ai_narrative": report_data.get("ai_audit_narrative", ""),
            "all_teams": report_data["all_teams"],
            "unread": unread_count(db, user.id),
        },
    )


@router.get("/api/reports/summary")
def api_reports_summary(
    period: str = Query("monthly"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    floor: int | None = Query(None),
    team: str | None = Query(None),
    db: Session = Depends(get_db),
):
    report_data = get_meeting_intelligence_report(
        db,
        period=period,
        custom_start=start_date,
        custom_end=end_date,
        floor_filter=floor,
        team_filter=team,
    )
    return JSONResponse(report_data)


@router.post("/api/reports/agent-audit")
def api_run_agent_audit(
    period: str = Form("monthly"),
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
    floor: int | None = Form(None),
    team: str | None = Form(None),
    user: m.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    result = run_meeting_audit(
        db,
        period=period,
        custom_start=start_date,
        custom_end=end_date,
        floor_filter=floor,
        team_filter=team,
    )
    return JSONResponse({
        "status": "success",
        "narrative": result.get("ai_audit_narrative", ""),
        "summary": result.get("summary", {}),
    })


@router.get("/api/reports/export")
def export_reports_csv(
    period: str = Query("monthly"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    floor: int | None = Query(None),
    team: str | None = Query(None),
    format: str = Query("csv"),
    db: Session = Depends(get_db),
):
    report_data = get_meeting_intelligence_report(
        db,
        period=period,
        custom_start=start_date,
        custom_end=end_date,
        floor_filter=floor,
        team_filter=team,
    )

    if format.lower() == "json":
        return Response(
            content=json.dumps(report_data["meetings"], indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=meeting_report_{period}.json"},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Meeting ID",
        "Title",
        "Meeting Type",
        "Date",
        "Time Range",
        "Duration (Hrs)",
        "Room Name",
        "Floor",
        "Team",
        "Organizer",
        "Invited Count",
        "Attended Count",
        "Absent Count",
        "Attendance %",
        "Allocated Chairs",
        "Chair Efficiency %",
        "Meeting Outcome",
        "Invited Attendees",
        "Attended Attendees",
        "Absent Attendees",
    ])

    for m_item in report_data["meetings"]:
        writer.writerow([
            m_item["id"],
            m_item["title"],
            m_item["meeting_type"],
            m_item["date"],
            m_item["time_display"],
            m_item["duration_hours"],
            m_item["room_name"],
            m_item["floor_label"],
            m_item["organizer_team"],
            m_item["organizer_name"],
            m_item["invited_count"],
            m_item["attended_count"],
            m_item["absent_count"],
            f"{m_item['attendance_pct']}%",
            m_item["allocated_chairs"],
            f"{m_item['chair_efficiency_pct']}%",
            m_item["outcome"],
            "; ".join(m_item["invited_attendees"]),
            "; ".join(m_item["attended_names"]),
            "; ".join(m_item["absent_names"]),
        ])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=meeting_report_{period}.csv"},
    )
