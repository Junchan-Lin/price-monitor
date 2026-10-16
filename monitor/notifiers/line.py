import httpx

from monitor.models import Event
from monitor.notifiers.base import NotifyError, format_message


class LineNotifier:
    """LINE Messaging API 的 push message。"""

    name = "line"

    def __init__(self, client: httpx.AsyncClient, access_token: str, user_id: str) -> None:
        self.client = client
        self.access_token = access_token
        self.user_id = user_id

    async def send(self, event: Event) -> None:
        try:
            response = await self.client.post(
                "https://api.line.me/v2/bot/message/push",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "to": self.user_id,
                    "messages": [{"type": "text", "text": format_message(event)}],
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise NotifyError(f"LINE HTTP {e.response.status_code}") from None
        except httpx.HTTPError as e:
            raise NotifyError(f"LINE {type(e).__name__}") from None
