from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import engine, Base, SessionLocal
from models import Settings
from routers import sync, summary, sessions

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    defaults = {
        "weekly_target_hours": "40",
        "daily_target_hours":  "8",
        "tracking_start_date": "2026-01-01",
    }
    for key, value in defaults.items():
        if not db.query(Settings).filter(Settings.key == key).first():
            db.add(Settings(key=key, value=value))
    db.commit()
    db.close()
    yield


app = FastAPI(title="Work Time Tracker", lifespan=lifespan)
app.include_router(sync.router)
app.include_router(summary.router)
app.include_router(sessions.router)
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
