import httpx

from monitor.models import Event
from monitor.notifiers.base import NotifyError, format_message


class TelegramNotifier:
    name = "telegram"

    def __init__(self, client: httpx.AsyncClient, bot_token: str, chat_id: str) -> None:
        self.client = client
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, event: Event) -> None:
        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": format_message(event)},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise NotifyError(f"Telegram HTTP {e.response.status_code}") from None
        except httpx.HTTPError as e:
            raise NotifyError(f"Telegram {type(e).__name__}") from None
