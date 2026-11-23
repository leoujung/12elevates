"""Production entrypoint. Reads configuration only from the environment; never prints secrets.

Run with:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import os

from sqlalchemy.orm import sessionmaker

from app.api.v1.routes import create_app
from app.core.db import make_engine

if not os.environ.get("APP_JWT_SECRET") or len(os.environ["APP_JWT_SECRET"]) < 32:
    raise RuntimeError("APP_JWT_SECRET must be set (32+ chars)")

_engine = make_engine()  # uses APP_DATABASE_URL
app = create_app(sessionmaker(bind=_engine))


# Serve the member dashboard from the same origin (no CORS needed in production).
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse

_DASH = Path(os.environ.get("APP_DASHBOARD_FILE", "/app/dashboard/index.html"))

@app.get("/", include_in_schema=False)
def dashboard():
    if not _DASH.exists():
        return HTMLResponse("<h1>Dashboard not bundled</h1>", status_code=503)
    return FileResponse(_DASH, media_type="text/html; charset=utf-8",
                        headers={"X-Robots-Tag": "noindex, nofollow"})

