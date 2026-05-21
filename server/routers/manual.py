from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ManualEntry, Settings
from schemas import ManualEntryIn, ManualEntryOut, SettingsOut, SettingsIn

router = APIRouter()


@router.get("/api/manual", response_model=list[ManualEntryOut])
def list_manual(db: Session = Depends(get_db)):
    return db.query(ManualEntry).order_by(ManualEntry.date.desc()).all()


@router.post("/api/manual", response_model=ManualEntryOut)
def add_manual(body: ManualEntryIn, db: Session = Depends(get_db)):
    entry = ManualEntry(date=body.date, hours=body.hours, note=body.note)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/api/manual/{entry_id}")
def delete_manual(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(ManualEntry).filter(ManualEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.get("/api/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    rows = {s.key: s.value for s in db.query(Settings).all()}
    return SettingsOut(
        weekly_target_hours=float(rows.get("weekly_target_hours", "40")),
        daily_target_hours=float(rows.get("daily_target_hours", "8")),
        tracking_start_date=date.fromisoformat(rows.get("tracking_start_date", "2026-01-01")),
    )


@router.put("/api/settings", response_model=SettingsOut)
def update_settings(body: SettingsIn, db: Session = Depends(get_db)):
    updates = {}
    if body.weekly_target_hours is not None:
        updates["weekly_target_hours"] = str(body.weekly_target_hours)
    if body.daily_target_hours is not None:
        updates["daily_target_hours"] = str(body.daily_target_hours)
    if body.tracking_start_date is not None:
        updates["tracking_start_date"] = body.tracking_start_date.isoformat()
    for key, value in updates.items():
        row = db.query(Settings).filter(Settings.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Settings(key=key, value=value))
    db.commit()
    return get_settings(db)
