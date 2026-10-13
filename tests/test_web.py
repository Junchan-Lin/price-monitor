import pytest
from fastapi.testclient import TestClient

from monitor.config import Settings
from monitor.web.app import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'web.db'}")
    with TestClient(create_app(settings, start_scheduler=False)) as client:
        yield client


def test_dashboard_and_event_pages_open(client):
    assert client.get("/").status_code == 200
    assert client.get("/events").status_code == 200


def test_add_and_delete_product(client):
    url = "http://shop-a.localhost:8001/products#P001"
    response = client.post("/products", data={"url": url, "threshold_pct": "7"})
    assert response.status_code == 200
    assert url in client.get("/").text

    assert client.get("/products/1").status_code == 200

    response = client.post("/products/1/delete", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert url not in response.text
    assert client.get("/products/1").status_code == 404


def test_unsupported_url_shows_error(client):
    response = client.post(
        "/products", data={"url": "https://example.com/x"}, headers={"HX-Request": "true"}
    )
    assert "不支援的網站" in response.text


def test_seed_urls_on_empty_database(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'seed.db'}",
        seed_urls=["http://shop-c.localhost:8001/item/P001"],
    )
    with TestClient(create_app(settings, start_scheduler=False)) as client:
        assert "http://shop-c.localhost:8001/item/P001" in client.get("/").text
