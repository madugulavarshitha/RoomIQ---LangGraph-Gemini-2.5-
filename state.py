"""
Strongly typed shared state passed between every LangGraph node.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentStatus(TypedDict, total=False):
    status: str  # IDLE | RUNNING | COMPLETED | WAITING | ERROR
    last_action: str
    confidence: float
    duration_ms: int


class OptimizationState(TypedDict, total=False):
    run_id: str
    user_request: str

    meeting_details: dict[str, Any]
    room_requirements: dict[str, Any]
    desk_requirements: dict[str, Any]

    room_inventory: list[dict[str, Any]]
    desk_inventory: list[dict[str, Any]]
    bookings: list[dict[str, Any]]
    occupancy_data: list[dict[str, Any]]

    demand_prediction: dict[str, Any]
    conflicts: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    reallocations: list[dict[str, Any]]
    notifications: list[dict[str, Any]]
    analytics: dict[str, Any]

    agent_status: dict[str, AgentStatus]
    confidence_scores: dict[str, float]
    audit_events: list[dict[str, Any]]

    need_reallocation: bool
    final_decision: str
