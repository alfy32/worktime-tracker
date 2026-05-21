from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Event
from schemas import SessionOut, SessionsResponse, PatchSession
from session_utils import build_sessions

router = APIRouter()


@router.get("/api/sessions/computers", response_model=list[str])
def list_computers(db: Session = Depends(get_db)):
    rows = db.query(Event.computer).distinct().all()
    return sorted(r.computer for r in rows)


@router.get("/api/sessions", response_model=SessionsResponse)
def list_sessions(
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
):
    now = datetime.now()
    all_events = db.query(Event).order_by(Event.timestamp).all()
    sessions = build_sessions(all_events, now)
    total = len(sessions)
    start = (page - 1) * per_page
    return SessionsResponse(
        sessions=sessions[start: start + per_page],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch("/api/sessions/{login_event_id}", response_model=SessionOut)
def patch_session(
    login_event_id: int,
    body: PatchSession,
    db: Session = Depends(get_db),
):
    now = datetime.now()
    event = db.query(Event).filter(
        Event.id == login_event_id,
        Event.action == "login",
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Session not found")

    event.is_work = body.is_work
    event.note = body.note
    db.commit()

    all_events = db.query(Event).filter(Event.computer == event.computer).all()
    sessions = build_sessions(all_events, now)
    session = next((s for s in sessions if s.id == login_event_id), None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found after update")
    return session
