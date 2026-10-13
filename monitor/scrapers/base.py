import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from monitor.scrapers.fetch import Fetcher


class ScrapeError(Exception):
    """爬取失敗的基底類別。"""


class FetchError(ScrapeError):
    """網路錯誤、逾時或 HTTP 錯誤。"""


class ParseError(ScrapeError):
    """找不到預期的欄位：網站結構可能已改版。"""


class UnsupportedSiteError(ScrapeError):
    """沒有對應這個網址的 adapter。"""


@dataclass(frozen=True)
class ProductSnapshot:
    name: str
    price: int
    stock: int


def parse_int(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        raise ParseError(f"無法從「{text.strip()}」解析出數字")
    return int(digits)


@contextmanager
def parse_errors() -> Iterator[None]:
    """把解析過程中的意外例外轉成 ParseError，視為網站結構可能已改版。"""
    try:
        yield
    except ParseError:
        raise
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as e:
        raise ParseError(f"解析失敗：{e!r}") from e


class Adapter(ABC):
    """一家網站一個 adapter：輸入網址，回傳商品快照。"""

    key: str
    display_name: str

    def matches(self, hostname: str) -> bool:
        """預設以網域的第一段比對，例如 shop-a.localhost → shop-a。"""
        return hostname.split(".")[0] == self.key

    @abstractmethod
    async def scrape(self, url: str, fetcher: "Fetcher") -> ProductSnapshot: ...


class HtmlAdapter(Adapter):
    """抓取網址本身的 HTML 再解析。"""

    async def scrape(self, url: str, fetcher: "Fetcher") -> ProductSnapshot:
        return self.parse(await fetcher.get(url), url)

    def parse(self, html: str, url: str) -> ProductSnapshot:
        with parse_errors():
            return self._parse(BeautifulSoup(html, "html.parser"), url)

    @abstractmethod
    def _parse(self, soup: BeautifulSoup, url: str) -> ProductSnapshot: ...


def require(element, what: str):
    if element is None:
        raise ParseError(f"找不到{what}")
    return element
