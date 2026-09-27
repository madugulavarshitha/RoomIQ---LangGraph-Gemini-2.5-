"""
RoomIQ Application Entrypoint
Run with: python app.py
"""
import os
import uvicorn
from app.database.database import Base, engine, session_scope
from app.services.simulation_service import seed_all

import sys

if __name__ == "__main__":
    # Ensure UTF-8 output encoding for console
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Ensure database tables exist and initial digital twin data is seeded
    Base.metadata.create_all(bind=engine)
    with session_scope() as db:
        seed_all(db, force=False)

    print("=" * 60)
    print("[*] RoomIQ Workplace AI Digital Twin running at:")
    print("--> http://localhost:8000/dashboard")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

