import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from monitor.config import Settings
from monitor.models import Event, EventDelivery, utcnow
from monitor.notifiers.base import Notifier, format_message
from monitor.notifiers.console import ConsoleNotifier
from monitor.notifiers.line import LineNotifier
from monitor.notifiers.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


def build_notifiers(settings: Settings, client: httpx.AsyncClient) -> list[Notifier]:
    """依設定啟用通知管道；Telegram 與 LINE 都沒設定時改用終端機輸出。"""
    notifiers: list[Notifier] = []
    if settings.telegram_bot_token and settings.telegram_chat_id:
        notifiers.append(
            TelegramNotifier(client, settings.telegram_bot_token, settings.telegram_chat_id)
        )
    if settings.line_channel_access_token and settings.line_user_id:
        notifiers.append(
            LineNotifier(client, settings.line_channel_access_token, settings.line_user_id)
        )
    return notifiers or [ConsoleNotifier()]


async def dispatch_pending(session: Session, notifiers: list[Notifier]) -> None:
    """對每個尚未通知的事件，用所有管道送出；已成功的管道不重送。

    全部管道都成功後才標記為已通知。
    """
    pending = session.scalars(
        select(Event).where(Event.notified_at.is_(None)).order_by(Event.id)
    ).all()
    for event in pending:
        deliveries = {d.channel: d for d in event.deliveries}
        all_ok = True
        for notifier in notifiers:
            delivery = deliveries.get(notifier.name)
            if delivery and delivery.success:
                continue
            if delivery is None:
                delivery = EventDelivery(channel=notifier.name)
                event.deliveries.append(delivery)
            delivery.last_attempt_at = utcnow()
            try:
                await notifier.send(event)
            except Exception as e:  # 單一管道失敗不影響其他管道
                logger.warning("事件 %s 透過 %s 送出失敗：%r", event.id, notifier.name, e)
                delivery.success, delivery.error = False, repr(e)
                all_ok = False
            else:
                delivery.success, delivery.error = True, None
        if all_ok:
            event.notified_at = utcnow()
        session.commit()


__all__ = ["Notifier", "build_notifiers", "dispatch_pending", "format_message"]
