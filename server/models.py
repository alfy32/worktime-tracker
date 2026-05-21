from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Float, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("computer", "timestamp", "action", name="uq_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    computer: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    is_work: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class ManualEntry(Base):
    __tablename__ = "manual_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[float] = mapped_column(Float, default=8.0)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
