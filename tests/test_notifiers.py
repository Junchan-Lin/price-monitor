import json

import httpx
import respx
from sqlalchemy import select

from monitor.config import Settings
from monitor.models import Event, Product
from monitor.notifiers import build_notifiers, dispatch_pending, format_message
from monitor.notifiers.console import ConsoleNotifier
from monitor.notifiers.line import LineNotifier
from monitor.notifiers.telegram import TelegramNotifier
from tests.conftest import FakeNotifier

TELEGRAM_URL = "https://api.telegram.org/botTOKEN/sendMessage"
LINE_URL = "https://api.line.me/v2/bot/message/push"


def make_event(session, type_="price_drop", old="1000", new="850") -> Event:
    product = Product(
        url="http://shop-a.localhost/products#P001", shop="shop-a", name="無線藍牙耳機"
    )
    event = Event(product=product, type=type_, old_value=old, new_value=new)
    session.add(event)
    session.commit()
    return event


def test_format_message(session_factory):
    with session_factory() as session:
        text = format_message(make_event(session))
    assert text.startswith("📉 降價｜無線藍牙耳機（飛鳥 3C）")
    assert "NT$1,000 → NT$850（-15.0%）" in text
    assert "http://shop-a.localhost/products#P001" in text


def test_build_notifiers_falls_back_to_console():
    client = httpx.AsyncClient()
    assert [type(n) for n in build_notifiers(Settings(), client)] == [ConsoleNotifier]
    both = Settings(
        telegram_bot_token="t",
        telegram_chat_id="c",
        line_channel_access_token="l",
        line_user_id="u",
    )
    assert [n.name for n in build_notifiers(both, client)] == ["telegram", "line"]


@respx.mock
async def test_telegram_payload(session_factory):
    route = respx.post(TELEGRAM_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    with session_factory() as session:
        event = make_event(session)
        async with httpx.AsyncClient() as client:
            await TelegramNotifier(client, "TOKEN", "42").send(event)
    body = json.loads(route.calls.last.request.content)
    assert body["chat_id"] == "42"
    assert "無線藍牙耳機" in body["text"]


@respx.mock
async def test_line_payload(session_factory):
    route = respx.post(LINE_URL).mock(return_value=httpx.Response(200, json={}))
    with session_factory() as session:
        event = make_event(session, "out_of_stock", "5", "0")
        async with httpx.AsyncClient() as client:
            await LineNotifier(client, "SECRET", "U123").send(event)
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer SECRET"
    body = json.loads(request.content)
    assert body["to"] == "U123"
    assert body["messages"][0]["type"] == "text"
    assert "缺貨" in body["messages"][0]["text"]


@respx.mock
async def test_failed_channel_keeps_event_pending_and_only_retries_that_channel(session_factory):
    telegram = respx.post(TELEGRAM_URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": True})]
    )
    fake = FakeNotifier()
    async with httpx.AsyncClient() as client:
        notifiers = [TelegramNotifier(client, "TOKEN", "42"), fake]
        with session_factory() as session:
            event = make_event(session)

            await dispatch_pending(session, notifiers)
            assert event.notified_at is None
            assert {d.channel: d.success for d in event.deliveries} == {
                "telegram": False,
                "fake": True,
            }

            await dispatch_pending(session, notifiers)
            assert event.notified_at is not None
            assert telegram.call_count == 2
            assert len(fake.sent) == 1  # 已成功的管道不重送


async def test_notified_events_are_not_resent(session_factory):
    fake = FakeNotifier()
    with session_factory() as session:
        make_event(session)
        await dispatch_pending(session, [fake])
        await dispatch_pending(session, [fake])
        assert len(fake.sent) == 1
        assert session.scalars(select(Event)).one().notified_at is not None
