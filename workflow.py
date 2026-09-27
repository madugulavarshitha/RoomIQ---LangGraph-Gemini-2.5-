"""
LangGraph orchestration for the workplace optimization workflow.

    START
      |
  Coordinator (init)
      |
  Demand Prediction
      |
  Occupancy Monitoring
      |
  Need Reallocation? --NO--> Analytics --> Coordinator (finalize) --> END
      |
     YES
      |
  Space Reallocation
      |
  Booking & Scheduling
      |
  Notification
      |
  Analytics
      |
  Coordinator (finalize)
      |
     END
"""
from __future__ import annotations

import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents import (
    analytics_agent,
    booking_agent,
    coordinator,
    demand_agent,
    notification_agent,
    occupancy_agent,
    reallocation_agent,
)
from app.database import models as m
from app.graph.state import OptimizationState


def _route_after_occupancy(state: OptimizationState) -> str:
    return "reallocate" if state.get("need_reallocation") else "skip_to_analytics"


def build_graph(db: Session, run_id: str):
    graph = StateGraph(OptimizationState)

    graph.add_node("coordinator_init", lambda s: coordinator.initialize(db, s, run_id))
    graph.add_node("demand_forecast", lambda s: demand_agent.run(db, s, run_id))
    graph.add_node("occupancy_monitoring", lambda s: occupancy_agent.run(db, s, run_id))
    graph.add_node("space_reallocation", lambda s: reallocation_agent.run(db, s, run_id))
    graph.add_node("booking_scheduling", lambda s: booking_agent.run(db, s, run_id))
    graph.add_node("notification", lambda s: notification_agent.run(db, s, run_id))
    graph.add_node("utilization_analytics", lambda s: analytics_agent.run(db, s, run_id))
    graph.add_node("coordinator_finalize", lambda s: coordinator.finalize(db, s, run_id))

    graph.set_entry_point("coordinator_init")
    graph.add_edge("coordinator_init", "demand_forecast")
    graph.add_edge("demand_forecast", "occupancy_monitoring")
    graph.add_conditional_edges(
        "occupancy_monitoring",
        _route_after_occupancy,
        {"reallocate": "space_reallocation", "skip_to_analytics": "utilization_analytics"},
    )
    graph.add_edge("space_reallocation", "booking_scheduling")
    graph.add_edge("booking_scheduling", "notification")
    graph.add_edge("notification", "utilization_analytics")
    graph.add_edge("utilization_analytics", "coordinator_finalize")
    graph.add_edge("coordinator_finalize", END)

    return graph.compile()


def run_optimization_workflow(db: Session, user_request: str, triggered_by: str | None = None) -> OptimizationState:
    run = m.AgentRun(triggered_by=triggered_by, status="RUNNING", summary="")
    db.add(run)
    db.flush()
    run_id = run.id

    app_graph = build_graph(db, run_id)
    initial_state: OptimizationState = {"user_request": user_request, "run_id": run_id}

    try:
        final_state = app_graph.invoke(initial_state)
    except Exception as exc:
        run.status = "ERROR"
        run.summary = f"Workflow failed: {exc}"
        db.commit()
        raise

    db.commit()
    return final_state
