import httpx
import pytest
import respx

from monitor.scrapers import ParseError, ProductSnapshot, get_adapter
from monitor.scrapers.fetch import Fetcher
from monitor.scrapers.pchome import PChomeAdapter
from tests.conftest import FIXTURES

URL = "https://24h.pchome.com.tw/prod/DYAJCH-1900JLHPE"


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


def test_selected_by_full_domain():
    assert get_adapter(URL).key == "pchome"
    assert (
        get_adapter("https://24h.pchome.com.tw/prod/DYAJCH-1900JLHPE?fq=/S/DYAJCH").key == "pchome"
    )


@pytest.mark.parametrize(
    "url",
    [URL, URL + "-000", URL + "?fq=/S/DYAJCH", URL + "#comment"],
)
def test_prod_id_from_url(url):
    assert PChomeAdapter.prod_id(url) == "DYAJCH-1900JLHPE"


def test_prod_id_missing_raises_parse_error():
    with pytest.raises(ParseError):
        PChomeAdapter.prod_id("https://24h.pchome.com.tw/region/DYAJ")


def test_parse_in_stock():
    snapshot = PChomeAdapter.parse_api(
        "DYAJCH-1900JLHPE", fixture("pchome_button"), fixture("pchome_search")
    )
    assert snapshot == ProductSnapshot("Apple 蘋果 AirPods Pro 3", 7490, 20)


def test_parse_out_of_stock():
    snapshot = PChomeAdapter.parse_api(
        "DYAJCH-1900JLHPE", fixture("pchome_button_out_of_stock"), fixture("pchome_search")
    )
    assert (snapshot.price, snapshot.stock) == (27478, 0)


@pytest.mark.parametrize(
    ("button", "search"),
    [
        ('[{"Id": "X", "Cost": 100, "Qty": 1, "ButtonType": "ForSale"}]', None),  # 欄位改名
        ("[]", None),  # 查無商品
        ("<html>503</html>", None),  # 回傳的不是 JSON
        (None, '{"Prods": []}'),  # 搜尋不到名稱
    ],
)
def test_changed_api_raises_parse_error(button, search):
    with pytest.raises(ParseError):
        PChomeAdapter.parse_api(
            "DYAJCH-1900JLHPE",
            button or fixture("pchome_button"),
            search or fixture("pchome_search"),
        )


@respx.mock
async def test_scrape_calls_both_apis():
    button = respx.get(url__startswith="https://ecapi-cdn.pchome.com.tw/").mock(
        return_value=httpx.Response(200, text=fixture("pchome_button"))
    )
    search = respx.get(url__startswith="https://ecshweb.pchome.com.tw/").mock(
        return_value=httpx.Response(200, text=fixture("pchome_search"))
    )
    async with httpx.AsyncClient() as client:
        fetcher = Fetcher(client, backoff_seconds=0, per_host_delay_seconds=0)
        snapshot = await get_adapter(URL).scrape(URL, fetcher)

    assert snapshot.price == 7490
    assert "id=DYAJCH-1900JLHPE-000" in str(button.calls.last.request.url)
    assert search.calls.last.request.url.params["q"] == "DYAJCH-1900JLHPE"
