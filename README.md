# RoomIQ – README

**RoomIQ** is a multi-agent AI workplace management system that helps organizations manage rooms, desks, bookings, occupancy, and space utilization.

### Key Features

* 🏢 Workplace Dashboard
* 🗺️ Office Map
* 📅 Smart Booking
* 🤖 7 AI Agents using LangGraph
* 📊 Demand Forecasting
* 👥 Occupancy Monitoring
* 🔄 AI Space Reallocation
* 📈 Utilization Analytics
* 🔔 Notifications
* 📝 Audit Logs

### Technology Stack

**FastAPI • Jinja2 • CSS • LangGraph • LangChain Core • Gemini 2.5 • SQLAlchemy • SQLite • Pandas • NumPy • Scikit-learn**

### AI Agents

1. Space Coordinator
2. Demand Prediction
3. Occupancy Monitoring
4. Space Reallocation
5. Booking & Scheduling
6. Notification
7. Utilization Analytics

### Installation

```bash
pip install fastapi uvicorn[standard]
pip install sqlalchemy
pip install langgraph langchain-core
pip install pandas scikit-learn numpy
pip install google-genai
```

### Run

```bash
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

### Objective

RoomIQ transforms static workplace allocation into a **data-driven, explainable, and AI-assisted optimization system**, helping organizations make better use of rooms, desks, and office space.
