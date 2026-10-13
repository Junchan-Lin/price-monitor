from typing import Protocol

from monitor.models import Event
from monitor.scrapers import ADAPTERS


class Notifier(Protocol):
    """通知管道：送出事件，失敗時拋出例外。"""

    name: str

    async def send(self, event: Event) -> None: ...


def _money(value: str | None) -> str:
    return f"NT${int(value):,}" if value and value.isdigit() else str(value)


def format_message(event: Event) -> str:
    product = event.product
    adapter = ADAPTERS.get(product.shop)
    shop = adapter.display_name if adapter else product.shop
    title = f"{product.name or product.url}（{shop}）"

    match event.type:
        case "price_drop" | "price_rise":
            old, new = int(event.old_value), int(event.new_value)
            pct = (new - old) / old * 100
            label = "📉 降價" if event.type == "price_drop" else "📈 漲價"
            body = f"{_money(event.old_value)} → {_money(event.new_value)}（{pct:+.1f}%）"
        case "out_of_stock":
            label, body = "⚠️ 缺貨", f"庫存 {event.old_value} → 0"
        case "restock":
            label, body = "✅ 補貨", f"庫存 0 → {event.new_value}"
        case "monitor_error":
            label, body = (
                "🚨 監控異常",
                f"連續失敗，請檢查網站是否改版或無法連線\n{event.new_value}",
            )
        case "monitor_recovered":
            label, body = "🔧 監控恢復", "已恢復正常爬取"
        case _:
            label, body = event.type, f"{event.old_value} → {event.new_value}"

    return f"{label}｜{title}\n{body}\n{product.url}"
