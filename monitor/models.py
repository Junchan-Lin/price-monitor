from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

EVENT_TYPES = (
    "price_drop",
    "price_rise",
    "out_of_stock",
    "restock",
    "monitor_error",
    "monitor_recovered",
)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    shop: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200), default="")
    threshold_pct: Mapped[float] = mapped_column(default=5.0)
    last_checked_at: Mapped[datetime | None]
    # ok / network_error / parse_error / pending（尚未檢查）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(default=0)

    snapshots: Mapped[list["Snapshot"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="Snapshot.id"
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="Event.id"
    )


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    price: Mapped[int]
    stock: Mapped[int]
    scraped_at: Mapped[datetime] = mapped_column(default=utcnow)

    product: Mapped[Product] = relationship(back_populates="snapshots")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    notified_at: Mapped[datetime | None]

    product: Mapped[Product] = relationship(back_populates="events")
    deliveries: Mapped[list["EventDelivery"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventDelivery(Base):
    __tablename__ = "event_deliveries"
    __table_args__ = (UniqueConstraint("event_id", "channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    success: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)
    last_attempt_at: Mapped[datetime] = mapped_column(default=utcnow)

    event: Mapped[Event] = relationship(back_populates="deliveries")


def init_db(database_url: str) -> sessionmaker:
    url = make_url(database_url)
    connect_args = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
