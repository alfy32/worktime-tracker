from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import get_db
from models import Event
from schemas import SyncRequest, SyncResponse

router = APIRouter()


@router.post("/api/sync", response_model=SyncResponse)
def sync_events(request: SyncRequest, db: Session = Depends(get_db)):
    inserted = 0
    skipped = 0
    for event in request.events:
        stmt = (
            sqlite_insert(Event)
            .values(
                computer=request.computer,
                timestamp=event.timestamp,
                action=event.action,
                is_work=True,
            )
            .on_conflict_do_nothing(index_elements=["computer", "timestamp", "action"])
        )
        result = db.execute(stmt)
        if result.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    db.commit()
    return SyncResponse(inserted=inserted, skipped=skipped)
