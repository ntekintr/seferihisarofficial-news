import json
from pathlib import Path

import pytest

from seferihisar.domain import parse_date
from seferihisar.store import Store


@pytest.fixture
def at():
    return parse_date("2026-10-10T10:00:00+03:00")


@pytest.fixture
def event():
    return json.loads(Path("tests/fixtures/items.json").read_text())[0]


@pytest.fixture
def source():
    return json.loads(Path("config/sources.json").read_text())[0]


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "state.sqlite")
    yield db
    db.close()
