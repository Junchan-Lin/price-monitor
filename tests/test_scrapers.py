import httpx
import pytest
import respx

from monitor.scrapers import ParseError, ProductSnapshot, UnsupportedSiteError, get_adapter
from monitor.scrapers.base import FetchError
from monitor.scrapers.fetch import Fetcher
from tests.conftest import fixture_html


@pytest.mark.parametrize(
    ("url", "fixture", "expected"),
    [
        (
            "http://shop-a.localhost/products#P001",
            "shop_a",
            ProductSnapshot("無線藍牙耳機", 1990, 25),
        ),
        (
            "http://shop-a.localhost/products#P002",
            "shop_a",
            ProductSnapshot("行動電源 10000mAh", 890, 0),
        ),
        (
            "http://shop-b.localhost/products#P001",
            "shop_b",
            ProductSnapshot("無線藍牙耳機", 1930, 25),
        ),
        (
            "http://shop-b.localhost/products#P002",
            "shop_b",
            ProductSnapshot("行動電源 10000mAh", 860, 0),
        ),
        ("http://shop-c.localhost/item/P001", "shop_c", ProductSnapshot("無線藍牙耳機", 2050, 25)),
        (
            "http://shop-c.localhost/item/P002",
            "shop_c_out_of_stock",
            ProductSnapshot("行動電源 10000mAh", 920, 0),
        ),
    ],
)
def test_adapters_parse_fixtures(url, fixture, expected):
    assert get_adapter(url).parse(fixture_html(fixture), url) == expected


@pytest.mark.parametrize(
    ("url", "fixture"),
    [
        ("http://shop-a.localhost/products#P001", "shop_a_redesigned"),
        ("http://shop-b.localhost/products#P001", "shop_b_redesigned"),
        ("http://shop-c.localhost/item/P001", "shop_c_redesigned"),
    ],
)
def test_redesigned_html_raises_parse_error(url, fixture):
    with pytest.raises(ParseError):
        get_adapter(url).parse(fixture_html(fixture), url)


def test_unknown_product_raises_parse_error():
    url = "http://shop-a.localhost/products#P999"
    with pytest.raises(ParseError):
        get_adapter(url).parse(fixture_html("shop_a"), url)


def test_adapter_selected_by_domain():
    assert get_adapter("http://shop-b:8001/products#P001").key == "shop-b"
    assert get_adapter("http://shop-c.example.com/item/P001").key == "shop-c"
    with pytest.raises(UnsupportedSiteError):
        get_adapter("https://www.example.com/item/1")


@respx.mock
async def test_fetcher_retries_then_succeeds():
    route = respx.get("http://shop-a.localhost/products").mock(
        side_effect=[
            httpx.ConnectTimeout("timeout"),
            httpx.Response(500),
            httpx.Response(200, text="ok"),
        ]
    )
    async with httpx.AsyncClient() as client:
        fetcher = Fetcher(client, backoff_seconds=0, per_host_delay_seconds=0)
        assert await fetcher.get("http://shop-a.localhost/products#P001") == "ok"
    assert route.call_count == 3


@respx.mock
async def test_fetcher_gives_up_after_three_retries():
    route = respx.get("http://shop-a.localhost/products").mock(
        side_effect=httpx.ConnectError("down")
    )
    async with httpx.AsyncClient() as client:
        fetcher = Fetcher(client, backoff_seconds=0, per_host_delay_seconds=0)
        with pytest.raises(FetchError):
            await fetcher.get("http://shop-a.localhost/products")
    assert route.call_count == 4  # 1 次 + 重試 3 次
