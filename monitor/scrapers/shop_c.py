from monitor.scrapers.base import HtmlAdapter, ProductSnapshot, parse_int, require


class ShopCAdapter(HtmlAdapter):
    """優選商城：商品詳細頁（schema.org 標記）。網址格式 /item/<商品編號>。"""

    key = "shop-c"
    display_name = "優選商城"

    def _parse(self, soup, url):
        product = require(soup.select_one('[itemtype="https://schema.org/Product"]'), "商品區塊")
        name = require(product.select_one('[itemprop="name"]'), "商品名稱").get_text(strip=True)
        price_tag = require(product.select_one('meta[itemprop="price"]'), "價格")
        price = parse_int(price_tag["content"])
        stock_text = require(product.select_one("#qty"), "庫存").get_text(strip=True)
        stock = 0 if "缺貨" in stock_text else parse_int(stock_text)
        return ProductSnapshot(name, price, stock)
