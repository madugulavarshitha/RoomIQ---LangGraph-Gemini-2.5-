from __future__ import annotations

import datetime as dt

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["now"] = dt.datetime.utcnow
templates.env.globals["today"] = dt.date.today
