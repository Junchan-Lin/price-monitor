"""在同一個程序內啟動 mock-shops，跑完整排程流程。"""

import httpx
import pytest
from sqlalchemy import select

from mock_shops.app import app as mock_app
from mock_shops.app import state
from monitor.models import Event, Product, Snapshot
from monitor.scheduler import run_cycle
from monitor.scrapers.fetch import Fetcher
from monitor.web.app import add_product
from tests.conftest import FakeNotifier

URLS = [
    "http://shop-a.localhost/products#P001",
    "http://shop-b.localhost/products#P003",
    "http://shop-c.localhost/item/P005",
]


@pytest.fixture
async def fetcher():
    state.reset()
    transport = httpx.ASGITransport(app=mock_app)
    async with httpx.AsyncClient(transport=transport) as client:
        yield Fetcher(client, backoff_seconds=0, per_host_delay_seconds=0)
    state.reset()


@pytest.fixture
def products(session_factory):
    with session_factory() as session:
        for url in URLS:
            add_product(session, url)


def event_types(session) -> list[tuple[str, str]]:
    return [(e.product.shop, e.type) for e in session.scalars(select(Event).order_by(Event.id))]


async def test_full_cycle_detects_changes_and_notifies(session_factory, fetcher, products):
    notifier = FakeNotifier()

    await run_cycle(session_factory, fetcher, [notifier])
    with session_factory() as session:
        assert session.query(Snapshot).count() == 3
        assert event_types(session) == []  # 第一輪只建立基準
        names = [p.name for p in session.scalars(select(Product).order_by(Product.id))]
        assert names == ["無線藍牙耳機", "USB-C 快充充電器 65W", "無線滑鼠"]

    state.set("shop-a", "P001", price=1590)  # 降價約 20%
    state.set("shop-b", "P003", stock=0)
    state.set("shop-c", "P005", price=720)  # 漲價約 1%，未達門檻
    await run_cycle(session_factory, fetcher, [notifier])

    with session_factory() as session:
        assert event_types(session) == [("shop-a", "price_drop"), ("shop-b", "out_of_stock")]
        assert all(e.notified_at for e in session.scalars(select(Event)))
    assert [t for _, t in notifier.sent] == ["price_drop", "out_of_stock"]


async def test_redesign_triggers_single_monitor_error_then_recovery(
    session_factory, fetcher, products
):
    notifier = FakeNotifier()
    await run_cycle(session_factory, fetcher, [notifier])

    state.redesigned["shop-c"] = True
    for _ in range(4):
        await run_cycle(session_factory, fetcher, [notifier])

    with session_factory() as session:
        product = session.scalars(select(Product).where(Product.shop == "shop-c")).one()
        assert product.status == "parse_error"
        assert product.consecutive_failures == 4
        assert event_types(session) == [("shop-c", "monitor_error")]  # 只通知一次
        others = session.scalars(select(Product).where(Product.shop != "shop-c")).all()
        assert all(p.status == "ok" for p in others)  # 不影響其他商品

    state.redesigned["shop-c"] = False
    await run_cycle(session_factory, fetcher, [notifier])
    with session_factory() as session:
        assert event_types(session)[-1] == ("shop-c", "monitor_recovered")
        product = session.scalars(select(Product).where(Product.shop == "shop-c")).one()
        assert (product.status, product.consecutive_failures) == ("ok", 0)
    assert [t for _, t in notifier.sent] == ["monitor_error", "monitor_recovered"]


async def test_network_error_is_recorded_separately(session_factory, fetcher):
    with session_factory() as session:
        add_product(session, "http://shop-c.localhost/item/P404")  # mock-shops 回 404
    await run_cycle(session_factory, fetcher, [FakeNotifier()])
    with session_factory() as session:
        product = session.scalars(select(Product)).one()
        assert product.status == "network_error"
        assert "404" in product.last_error
