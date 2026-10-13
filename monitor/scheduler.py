"""每一輪排程：爬取所有監控商品 → 存快照 → 偵測變化 → 送出通知。"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from monitor.detector import State, detect
from monitor.models import Event, Product, Snapshot, utcnow
from monitor.notifiers import Notifier, dispatch_pending
from monitor.scrapers import FetchError, ParseError, get_adapter
from monitor.scrapers.fetch import Fetcher

logger = logging.getLogger(__name__)

FAILURE_LIMIT = 3


def _record_failure(session: Session, product: Product, status: str, message: str) -> None:
    product.status = status
    product.last_error = message
    product.consecutive_failures += 1
    logger.warning(
        "%s 爬取失敗（%s 第 %d 次）：%s", product.url, status, product.consecutive_failures, message
    )
    if product.consecutive_failures == FAILURE_LIMIT:  # 只在達到門檻那一次通知
        label = "網站結構可能已改版" if status == "parse_error" else "網路錯誤"
        session.add(Event(product=product, type="monitor_error", new_value=f"{label}：{message}"))


async def check_product(session: Session, product: Product, fetcher: Fetcher) -> None:
    product.last_checked_at = utcnow()
    try:
        snapshot = await get_adapter(product.url).scrape(product.url, fetcher)
    except FetchError as e:
        _record_failure(session, product, "network_error", str(e))
        return
    except ParseError as e:
        _record_failure(session, product, "parse_error", str(e))
        return

    prev = session.scalars(
        select(Snapshot).where(Snapshot.product_id == product.id).order_by(Snapshot.id.desc())
    ).first()
    prev_state = State(prev.price, prev.stock) if prev else None
    new_state = State(snapshot.price, snapshot.stock)

    session.add(Snapshot(product=product, price=snapshot.price, stock=snapshot.stock))
    for change in detect(prev_state, new_state, product.threshold_pct):
        session.add(
            Event(
                product=product,
                type=change.type,
                old_value=change.old_value,
                new_value=change.new_value,
            )
        )

    if product.consecutive_failures >= FAILURE_LIMIT:
        session.add(Event(product=product, type="monitor_recovered"))
    product.name = snapshot.name
    product.status = "ok"
    product.last_error = None
    product.consecutive_failures = 0


async def run_cycle(
    session_factory: sessionmaker, fetcher: Fetcher, notifiers: list[Notifier]
) -> None:
    with session_factory() as session:
        for product in session.scalars(select(Product).order_by(Product.id)).all():
            await check_product(session, product, fetcher)
            session.commit()  # 逐一提交，單一商品失敗不影響其他商品
        await dispatch_pending(session, notifiers)


def create_scheduler(
    interval_minutes: float,
    session_factory: sessionmaker,
    fetcher: Fetcher,
    notifiers: list[Notifier],
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cycle,
        "interval",
        minutes=interval_minutes,
        args=[session_factory, fetcher, notifiers],
        next_run_time=datetime.now(),  # 啟動後立即執行一輪
        max_instances=1,
        coalesce=True,
    )
    return scheduler
