from urllib.parse import urlsplit

from monitor.scrapers.base import HtmlAdapter, ParseError, ProductSnapshot, parse_int, require


class ShopBAdapter(HtmlAdapter):
    """樂購網：卡片網格。網址格式 /products#<商品編號>。"""

    key = "shop-b"
    display_name = "樂購網"

    def _parse(self, soup, url):
        sku = urlsplit(url).fragment
        if not sku:
            raise ParseError("網址缺少商品編號（#P001）")
        card = require(
            soup.find("div", class_="card", attrs={"data-code": sku}), f"商品 {sku} 的卡片"
        )
        name = require(card.find("h3"), "商品名稱").get_text(strip=True)
        price = parse_int(require(card.select_one(".amount"), "價格").get_text())
        stock_text = require(card.select_one(".avail"), "庫存").get_text(strip=True)
        stock = 0 if "售完" in stock_text else parse_int(stock_text)
        return ProductSnapshot(name, price, stock)
