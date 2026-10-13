import json
import re
from urllib.parse import quote, urlsplit

from monitor.scrapers.base import Adapter, ParseError, ProductSnapshot, parse_errors

# PChome 前端使用的 API。商品頁 HTML 會擋非瀏覽器的請求，所以改用 API 取得相同的公開資訊。
BUTTON_API = (
    "https://ecapi-cdn.pchome.com.tw/ecshop/prodapi/v2/prod/button"
    "&id={id}-000&fields=Id,Price,Qty,ButtonType"
)
SEARCH_API = "https://ecshweb.pchome.com.tw/search/v4.3/all/results?q={id}&page=1"

PROD_ID = re.compile(r"/prod/([A-Z0-9]+-[A-Z0-9]+)")


class PChomeAdapter(Adapter):
    """PChome 24h 購物。網址格式 https://24h.pchome.com.tw/prod/<商品編號>。"""

    key = "pchome"
    display_name = "PChome 24h"

    def matches(self, hostname):
        return hostname == "24h.pchome.com.tw"

    async def scrape(self, url, fetcher):
        prod_id = self.prod_id(url)
        button = await fetcher.get(BUTTON_API.format(id=quote(prod_id)))
        search = await fetcher.get(SEARCH_API.format(id=quote(prod_id)))
        return self.parse_api(prod_id, button, search)

    @staticmethod
    def prod_id(url: str) -> str:
        match = PROD_ID.search(urlsplit(url).path)
        if not match:
            raise ParseError(f"網址中找不到商品編號：{url}")
        return match.group(1)

    @staticmethod
    def parse_api(prod_id: str, button_json: str, search_json: str) -> ProductSnapshot:
        with parse_errors():
            [item] = json.loads(button_json)
            price = int(item["Price"]["P"])
            # 缺貨時 ButtonType 為 OrderRefill（補貨中），Qty 為 0
            stock = int(item["Qty"]) if item["ButtonType"] == "ForSale" else 0

            prods = json.loads(search_json).get("Prods") or []
            name = next((p["Name"] for p in prods if p["Id"] == prod_id), None)
            if not name:
                raise ParseError(f"搜尋結果中找不到商品 {prod_id} 的名稱")
            return ProductSnapshot(name, price, stock)
