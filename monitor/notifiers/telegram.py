import httpx

from monitor.models import Event
from monitor.notifiers.base import format_message


class TelegramNotifier:
    name = "telegram"

    def __init__(self, client: httpx.AsyncClient, bot_token: str, chat_id: str) -> None:
        self.client = client
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, event: Event) -> None:
        response = await self.client.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": format_message(event)},
        )
        response.raise_for_status()
