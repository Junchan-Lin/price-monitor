from monitor.models import Event
from monitor.notifiers.base import format_message


class ConsoleNotifier:
    name = "console"

    async def send(self, event: Event) -> None:
        print(f"\n🔔 [通知]\n{format_message(event)}\n", flush=True)
