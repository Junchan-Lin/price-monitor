"""比較新舊快照並產生事件。純邏輯，不碰資料庫。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class State:
    price: int
    stock: int


@dataclass(frozen=True)
class Change:
    type: str
    old_value: str
    new_value: str


def detect(prev: State | None, new: State, threshold_pct: float) -> list[Change]:
    if prev is None:  # 第一筆快照只建立基準
        return []

    changes = []
    diff = new.price - prev.price
    # 以整數運算比較，避免浮點誤差讓剛好等於門檻的變動被漏掉
    if diff and prev.price > 0 and abs(diff) * 100 >= threshold_pct * prev.price:
        kind = "price_drop" if diff < 0 else "price_rise"
        changes.append(Change(kind, str(prev.price), str(new.price)))

    if prev.stock > 0 and new.stock == 0:
        changes.append(Change("out_of_stock", str(prev.stock), str(new.stock)))
    elif prev.stock == 0 and new.stock > 0:
        changes.append(Change("restock", str(prev.stock), str(new.stock)))

    return changes
