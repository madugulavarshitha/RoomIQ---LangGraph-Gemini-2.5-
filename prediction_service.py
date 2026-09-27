"""
Demand prediction using Pandas for feature engineering and a
Scikit-learn model for the actual regression, per RULE 7.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as m

HOURS = list(range(8, 19))  # 08:00 - 18:00


def _historical_frame(db: Session) -> pd.DataFrame:
    bookings = list(db.scalars(select(m.Booking)))
    rows = []
    for b in bookings:
        rows.append(
            {
                "day_of_week": b.start_time.weekday(),
                "hour": b.start_time.hour,
                "duration_hr": (b.end_time - b.start_time).total_seconds() / 3600,
                "attendees": b.expected_attendees,
                "room_capacity": b.room.capacity if b.room else 6,
                "floor": b.room.floor if b.room else 1,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["day_of_week", "hour", "duration_hr", "attendees", "room_capacity", "floor"])
    return pd.DataFrame(rows)


def _train_demand_model(df: pd.DataFrame) -> GradientBoostingRegressor | None:
    if len(df) < 8:
        return None
    # Aggregate historical booking counts per (day_of_week, hour) as the
    # regression target — i.e. "how many concurrent room requests happen here".
    grouped = df.groupby(["day_of_week", "hour"]).size().reset_index(name="demand_count")
    X = grouped[["day_of_week", "hour"]].values
    y = grouped["demand_count"].values
    model = GradientBoostingRegressor(n_estimators=80, max_depth=2, random_state=42)
    model.fit(X, y)
    return model


def predict_demand(db: Session, target_day: dt.date | None = None) -> dict:
    target_day = target_day or dt.date.today()
    dow = target_day.weekday()

    df = _historical_frame(db)
    model = _train_demand_model(df)

    hourly = []
    for hour in HOURS:
        if model is not None:
            pred = float(model.predict(np.array([[dow, hour]]))[0])
        else:
            # Cold-start heuristic: bell curve peaking mid-morning / early afternoon.
            pred = max(0.5, 6 - abs(hour - 10.5) * 1.1)
        room_level = _bucket(pred, low=2, high=6)
        desk_level = _bucket(pred * 1.6, low=3, high=9)
        hourly.append(
            {
                "hour": f"{hour:02d}:00",
                "predicted_room_demand": round(pred, 1),
                "room_level": room_level,
                "predicted_desk_demand": round(pred * 1.6, 1),
                "desk_level": desk_level,
            }
        )

    peak = max(hourly, key=lambda h: h["predicted_room_demand"]) if hourly else None
    floor_demand = _floor_level_demand(df, dow)

    return {
        "date": str(target_day),
        "day_of_week": target_day.strftime("%A"),
        "hourly": hourly,
        "peak_hour": peak["hour"] if peak else None,
        "floor_demand": floor_demand,
        "model": "GradientBoostingRegressor" if model is not None else "cold_start_heuristic",
    }


def _bucket(value: float, *, low: float, high: float) -> str:
    if value >= high:
        return "VERY HIGH" if value >= high * 1.3 else "HIGH"
    if value >= low:
        return "MEDIUM"
    return "LOW"


def _floor_level_demand(df: pd.DataFrame, dow: int) -> list[dict]:
    if df.empty:
        return []
    subset = df[df["day_of_week"] == dow]
    if subset.empty:
        subset = df
    grouped = subset.groupby("floor").size().reset_index(name="bookings")
    total = grouped["bookings"].sum() or 1
    grouped["share_pct"] = (grouped["bookings"] / total * 100).round(1)
    return grouped.sort_values("bookings", ascending=False).to_dict(orient="records")
