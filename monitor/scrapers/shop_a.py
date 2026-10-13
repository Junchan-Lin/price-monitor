from urllib.parse import urlsplit

from monitor.scrapers.base import HtmlAdapter, ParseError, ProductSnapshot, parse_int, require


class ShopAAdapter(HtmlAdapter):
    """飛鳥 3C：表格列表。網址格式 /products#<商品編號>。"""

    key = "shop-a"
    display_name = "飛鳥 3C"

    def _parse(self, soup, url):
        sku = urlsplit(url).fragment
        if not sku:
            raise ParseError("網址缺少商品編號（#P001）")
        table = require(soup.select_one("table.price-table"), "商品表格")
        row = require(table.find("tr", id=sku), f"商品 {sku} 的表格列")
        name = require(row.select_one("td.name"), "商品名稱").get_text(strip=True)
        price = parse_int(require(row.select_one("td.price"), "價格").get_text())
        stock_text = require(row.select_one("td.stock"), "庫存").get_text(strip=True)
        stock = 0 if stock_text == "缺貨" else parse_int(stock_text)
        return ProductSnapshot(name, price, stock)
