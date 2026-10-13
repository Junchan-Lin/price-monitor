import pytest

from monitor.detector import Change, State, detect


def types(changes: list[Change]) -> list[str]:
    return [c.type for c in changes]


def test_first_snapshot_only_sets_baseline():
    assert detect(None, State(100, 0), 5) == []


@pytest.mark.parametrize(
    ("new_price", "expected"),
    [
        (95, ["price_drop"]),  # 剛好 5%
        (96, []),  # 4%，未達門檻
        (105, ["price_rise"]),
        (104, []),
        (100, []),
    ],
)
def test_price_threshold_boundary(new_price, expected):
    assert types(detect(State(100, 10), State(new_price, 10), 5)) == expected


def test_threshold_boundary_without_float_error():
    # 0.1 + 0.2 這類浮點誤差不應讓剛好等於門檻的變動被漏掉
    assert types(detect(State(1990, 1), State(1990 - 199, 1), 10)) == ["price_drop"]


def test_price_change_records_values():
    [change] = detect(State(1000, 5), State(800, 5), 5)
    assert change == Change("price_drop", "1000", "800")


def test_out_of_stock_and_restock_ignore_threshold():
    assert types(detect(State(100, 3), State(100, 0), 50)) == ["out_of_stock"]
    assert types(detect(State(100, 0), State(100, 7), 50)) == ["restock"]


def test_stock_quantity_change_is_not_an_event():
    assert detect(State(100, 10), State(100, 3), 5) == []


def test_price_and_stock_change_together():
    assert types(detect(State(100, 5), State(80, 0), 5)) == ["price_drop", "out_of_stock"]
