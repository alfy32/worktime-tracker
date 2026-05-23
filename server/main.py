from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from database import engine, Base, SessionLocal
from models import Settings
from routers import sync, summary, sessions, manual

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        defaults = {
            "weekly_target_hours": "40",
            "daily_target_hours":  "8",
            "tracking_start_date": "2026-01-01",
        }
        for key, value in defaults.items():
            if not db.query(Settings).filter(Settings.key == key).first():
                db.add(Settings(key=key, value=value))
        db.commit()
    finally:
        db.close()
    yield


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith((".html", ".js")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app = FastAPI(title="Work Time Tracker", lifespan=lifespan)
app.add_middleware(NoCacheStaticMiddleware)
app.include_router(sync.router)
app.include_router(summary.router)
app.include_router(sessions.router)
app.include_router(manual.router)
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
