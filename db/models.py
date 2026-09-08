from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base


class BurnRateSample(Base):
    __tablename__ = "burn_rate_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slo_name: Mapped[str] = mapped_column(String(255), index=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    budget_remaining_pct: Mapped[float] = mapped_column(Float)
    burn_rate_1h: Mapped[float] = mapped_column(Float)
    burn_rate_6h: Mapped[float] = mapped_column(Float)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slo_name: Mapped[str] = mapped_column(String(255), index=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    burn_rate: Mapped[float] = mapped_column(Float)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(32))  # "deploy" | "pipeline"
    source_system: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class CorrelationEvent(Base):
    __tablename__ = "correlation_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_event_id: Mapped[int] = mapped_column(ForeignKey("alert_events.id"), index=True)
    change_event_id: Mapped[int | None] = mapped_column(ForeignKey("change_events.id"), nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(32))
    source_system: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
