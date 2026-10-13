import asyncio
import time
from urllib.parse import urlsplit

import httpx

from monitor.scrapers.base import FetchError

USER_AGENT = "CodeSky-PriceMonitor/0.1 (+price monitoring bot)"


def make_client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=10, headers={"User-Agent": USER_AGENT}, follow_redirects=True, **kwargs
    )


class Fetcher:
    """抓取網頁：失敗時重試（間隔遞增），同一網站的請求之間保持間隔。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        retries: int = 3,
        backoff_seconds: float = 1.0,
        per_host_delay_seconds: float = 1.0,
    ) -> None:
        self.client = client
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.per_host_delay_seconds = per_host_delay_seconds
        self._last_request: dict[str, float] = {}

    async def _wait_for_host(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.per_host_delay_seconds - (time.monotonic() - last)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_request[host] = time.monotonic()

    async def get(self, url: str) -> str:
        host = urlsplit(url).hostname or ""
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                await asyncio.sleep(self.backoff_seconds * attempt)
            await self._wait_for_host(host)
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as e:
                last_error = e
        raise FetchError(f"{type(last_error).__name__}: {last_error}") from last_error
