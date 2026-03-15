"""Shared pytest fixtures for toyota_api tests."""

import json
import time
from pathlib import Path

import pytest

from toyota_api.auth import ToyotaAuth
from toyota_api.client import ToyotaClient


@pytest.fixture
def fixture_dir() -> Path:
    """Path to tests/fixtures/ directory."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def load_fixture(fixture_dir: Path):
    """Return a helper that loads a JSON fixture by name (without .json)."""

    def _load(name: str):
        path = fixture_dir / f"{name}.json"
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    return _load


@pytest.fixture
def mock_auth(load_fixture) -> ToyotaAuth:
    """ToyotaAuth with tokens pre-set (no real login)."""
    auth = ToyotaAuth()
    token_data = load_fixture("token_response")
    auth._access_token = token_data["access_token"]
    auth._refresh_token = token_data["refresh_token"]
    auth._expires_at = time.monotonic() + int(token_data.get("expires_in", 3600))
    auth._guid = "00000000-0000-0000-0000-000000000001"
    return auth


@pytest.fixture
def mock_client(mock_auth: ToyotaAuth) -> ToyotaClient:
    """ToyotaClient with mocked auth (already logged in)."""
    client = ToyotaClient("testuser", "testpass")
    client._auth = mock_auth
    return client
