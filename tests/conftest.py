from pathlib import Path

import pytest

from monitor.models import init_db

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_html(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text()


@pytest.fixture
def session_factory(tmp_path):
    return init_db(f"sqlite:///{tmp_path / 'test.db'}")


class FakeNotifier:
    def __init__(self, name: str = "fake", fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.sent = []

    async def send(self, event) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append((event.id, event.type))
