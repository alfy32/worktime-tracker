from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from database import Base
from models import Event, ManualEntry, Settings
from datetime import datetime, date


def test_tables_create():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    db.add(Event(computer="ubuntu", timestamp=datetime(2026, 5, 20, 9, 0), action="login"))
    db.add(ManualEntry(date=date(2026, 1, 1), hours=8.0, note="New Years Day"))
    db.add(Settings(key="weekly_target_hours", value="40"))
    db.commit()

    assert db.query(Event).count() == 1
    assert db.query(ManualEntry).count() == 1
    assert db.query(Settings).count() == 1
    db.close()


def test_event_unique_constraint():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    ts = datetime(2026, 5, 20, 9, 0)
    db.add(Event(computer="ubuntu", timestamp=ts, action="login"))
    db.commit()

    from sqlalchemy.exc import IntegrityError
    import pytest
    with pytest.raises(IntegrityError):
        db.add(Event(computer="ubuntu", timestamp=ts, action="login"))
        db.commit()
    db.close()
