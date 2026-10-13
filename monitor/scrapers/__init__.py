from urllib.parse import urlsplit

from monitor.scrapers.base import (
    Adapter,
    FetchError,
    HtmlAdapter,
    ParseError,
    ProductSnapshot,
    ScrapeError,
    UnsupportedSiteError,
)
from monitor.scrapers.pchome import PChomeAdapter
from monitor.scrapers.shop_a import ShopAAdapter
from monitor.scrapers.shop_b import ShopBAdapter
from monitor.scrapers.shop_c import ShopCAdapter

ADAPTERS: dict[str, Adapter] = {
    a.key: a for a in (ShopAAdapter(), ShopBAdapter(), ShopCAdapter(), PChomeAdapter())
}


def get_adapter(url: str) -> Adapter:
    """依網址的網域選用 adapter。"""
    hostname = urlsplit(url).hostname or ""
    for adapter in ADAPTERS.values():
        if adapter.matches(hostname):
            return adapter
    raise UnsupportedSiteError(f"不支援的網站：{url}")


__all__ = [
    "ADAPTERS",
    "Adapter",
    "HtmlAdapter",
    "FetchError",
    "ParseError",
    "ProductSnapshot",
    "ScrapeError",
    "UnsupportedSiteError",
    "get_adapter",
]
