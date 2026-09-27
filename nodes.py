"""
Node function registry — re-exports each agent's `run` (or coordinator's
`initialize`/`finalize`) so the workflow module has one place to look up
"what does this LangGraph node actually call". The wiring itself
(edges, conditional routing) lives in workflow.py.
"""
from __future__ import annotations

from app.agents import (
    analytics_agent,
    booking_agent,
    coordinator,
    demand_agent,
    notification_agent,
    occupancy_agent,
    reallocation_agent,
)

NODES = {
    "coordinator_init": coordinator.initialize,
    "demand_forecast": demand_agent.run,
    "occupancy_monitoring": occupancy_agent.run,
    "space_reallocation": reallocation_agent.run,
    "booking_scheduling": booking_agent.run,
    "notification": notification_agent.run,
    "utilization_analytics": analytics_agent.run,
    "coordinator_finalize": coordinator.finalize,
}
