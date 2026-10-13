"""三家模擬商城共用的商品資料，以及隨機變動價格與庫存的邏輯。"""

import random
from dataclasses import dataclass

SHOPS = {
    "shop-a": "飛鳥 3C",
    "shop-b": "樂購網",
    "shop-c": "優選商城",
}

# (商品編號, 名稱, 基準價格, 基準庫存)
CATALOG = [
    ("P001", "無線藍牙耳機", 1990, 25),
    ("P002", "行動電源 10000mAh", 890, 40),
    ("P003", "USB-C 快充充電器 65W", 1290, 18),
    ("P004", "機械式鍵盤", 2490, 9),
    ("P005", "無線滑鼠", 690, 60),
    ("P006", "27 吋 4K 螢幕", 8990, 5),
]

# 每家商城相對於基準價格的定價係數，讓各家價格略有不同
PRICE_FACTORS = {"shop-a": 1.0, "shop-b": 0.97, "shop-c": 1.03}


@dataclass
class Item:
    sku: str
    name: str
    price: int
    stock: int


def round_price(value: float) -> int:
    return max(10, int(round(value / 10)) * 10)


class ShopState:
    """所有商城目前的商品狀態，以及是否處於「改版」模式。"""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Item]] = {}
        self.redesigned: dict[str, bool] = {}
        self.reset()

    def reset(self) -> None:
        self.items = {
            shop: {
                sku: Item(sku, name, round_price(price * PRICE_FACTORS[shop]), stock)
                for sku, name, price, stock in CATALOG
            }
            for shop in SHOPS
        }
        self.redesigned = {shop: False for shop in SHOPS}

    def set(self, shop: str, sku: str, price: int | None = None, stock: int | None = None) -> Item:
        item = self.items[shop][sku]
        if price is not None:
            item.price = price
        if stock is not None:
            item.stock = stock
        return item

    def mutate(self, rng: random.Random | None = None) -> list[dict]:
        """每家商城隨機挑 1 到 2 個商品調整價格或切換庫存，回傳變動清單。"""
        rng = rng or random.Random()
        changes = []
        for shop, items in self.items.items():
            for item in rng.sample(list(items.values()), k=rng.randint(1, 2)):
                before = {"price": item.price, "stock": item.stock}
                if rng.random() < 0.7:
                    pct = rng.choice([rng.uniform(-0.20, -0.05), rng.uniform(0.05, 0.15)])
                    item.price = round_price(item.price * (1 + pct))
                elif item.stock > 0:
                    item.stock = 0
                else:
                    item.stock = rng.randint(5, 50)
                after = {"price": item.price, "stock": item.stock}
                changes.append({"shop": shop, "sku": item.sku, "before": before, "after": after})
        return changes
