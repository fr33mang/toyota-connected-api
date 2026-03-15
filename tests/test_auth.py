"""Tests for toyota_api.auth: PKCE helpers, JWT parsing, callbacks, ToyotaAuth flow."""

import base64
import json
import re
import time

import httpx
import pytest
import respx

from toyota_api.auth import (
    ToyotaAuth,
    _basic_auth,
    _fill_callbacks,
    _guid_from_jwt,
    _pkce_code_challenge,
    _pkce_code_verifier,
)
from toyota_api.const import AUTH_BASE_URL, JSON_REALM_PATH, OAUTH_REALM_PATH

# ----- PKCE and helpers -----


def test_pkce_code_verifier_length():
    """Verifier is 43–128 chars and URL-safe."""
    for _ in range(20):
        v = _pkce_code_verifier()
        assert 43 <= len(v) <= 128
        assert v.isascii()
        assert "+" not in v and "/" not in v  # url-safe base64


def test_pkce_code_challenge():
    """S256 code challenge is deterministic from verifier."""
    verifier = "a" * 43
    ch = _pkce_code_challenge(verifier)
    assert isinstance(ch, str)
    assert ch.isascii()
    assert "+" not in ch and "/" not in ch
    # Same verifier -> same challenge
    assert _pkce_code_challenge(verifier) == ch


def test_guid_from_jwt():
    """Extract sub (user guid) from JWT access_token."""
    payload = {"sub": "00000000-0000-0000-0000-000000000001"}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    token = f"header.{payload_b64}.sig"
    assert _guid_from_jwt(token) == "00000000-0000-0000-0000-000000000001"
    assert _guid_from_jwt("bad") is None
    assert _guid_from_jwt("a.b") is None


def test_fill_callbacks():
    """Callbacks get input values set by name."""
    callbacks = [
        {"type": "NameCallback", "input": [{"name": "IDToken1", "value": ""}]},
        {"type": "NameCallback", "input": [{"name": "IDToken2", "value": ""}]},
    ]
    filled = _fill_callbacks(callbacks, {"IDToken1": "GB", "IDToken2": "en-GB"})
    assert filled[0]["input"][0]["value"] == "GB"
    assert filled[1]["input"][0]["value"] == "en-GB"
    # Unmentioned name unchanged
    filled2 = _fill_callbacks(callbacks, {"IDToken1": "only"})
    assert filled2[0]["input"][0]["value"] == "only"
    assert filled2[1]["input"][0]["value"] == ""


def test_basic_auth():
    """Basic auth header value is base64(username:password)."""
    raw = base64.b64decode(_basic_auth("oneapp", "oneapp"))
    assert raw == b"oneapp:oneapp"


# ----- ToyotaAuth with respx -----


def _auth_authenticate_url(base: str = AUTH_BASE_URL) -> str:
    return f"{base.rstrip('/')}{JSON_REALM_PATH}/authenticate?authIndexType=service&authIndexValue=oneapp"


def _auth_token_url(base: str = AUTH_BASE_URL) -> str:
    return f"{base.rstrip('/')}{OAUTH_REALM_PATH}/access_token"


def _auth_authorize_url(base: str = AUTH_BASE_URL) -> str:
    return f"{base.rstrip('/')}{OAUTH_REALM_PATH}/authorize"


def _auth_revoke_url(base: str = AUTH_BASE_URL) -> str:
    return f"{base.rstrip('/')}{OAUTH_REALM_PATH}/token/revoke"


@respx.mock
async def test_login_flow(load_fixture):
    """Full login: authenticate (locale -> username -> password -> tokenId), authorize, token exchange."""
    auth_url = _auth_authenticate_url()
    token_url = _auth_token_url()
    auth_id = "test-auth-id"

    # 1) Empty POST -> locale callbacks
    locale_data = load_fixture("auth_callbacks")
    locale_data["authId"] = auth_id

    # 2) Locale submitted -> username callbacks
    username_callbacks = {
        "authId": auth_id,
        "callbacks": [
            {
                "type": "NameCallback",
                "output": [{"name": "prompt", "value": "User Name"}],
                "input": [{"name": "IDToken1", "value": ""}, {"name": "IDToken2", "value": ""}],
            },
        ],
    }

    # 3) Username submitted -> password callbacks
    password_callbacks = {
        "authId": auth_id,
        "callbacks": [
            {
                "type": "PasswordCallback",
                "output": [{"name": "prompt", "value": "Password"}],
                "input": [{"name": "IDToken1", "value": ""}, {"name": "IDToken2", "value": ""}],
            },
        ],
    }

    # 4) Password submitted -> tokenId (session established)
    token_id_response = {"tokenId": "session-token", "successUrl": "/"}

    auth_responses = [
        httpx.Response(200, json=locale_data),
        httpx.Response(200, json=username_callbacks),
        httpx.Response(200, json=password_callbacks),
        httpx.Response(200, json=token_id_response),
    ]
    respx.post(auth_url).mock(side_effect=auth_responses)

    # GET authorize -> 302 with code (URL has query params from auth)
    authorize_pattern = re.compile(r"^" + re.escape(_auth_authorize_url()) + r"\?")
    respx.get(url=authorize_pattern).mock(
        return_value=httpx.Response(302, headers={"location": "com.toyota.oneapp:/oauth2Callback?code=FAKE_AUTH_CODE"})
    )

    # POST access_token -> tokens
    token_data = load_fixture("token_response")
    respx.post(token_url).mock(return_value=httpx.Response(200, json=token_data))

    auth = ToyotaAuth()
    await auth.login("user", "pass")

    assert auth.access_token == token_data["access_token"]
    assert auth.guid == "00000000-0000-0000-0000-000000000001"


@respx.mock
async def test_refresh(load_fixture):
    """Refresh updates access_token from refresh_token."""
    token_url = _auth_token_url()
    token_data = load_fixture("token_response")
    token_data["access_token"] = "new_access_token"
    token_data["expires_in"] = 3600
    respx.post(token_url).mock(return_value=httpx.Response(200, json=token_data))

    auth = ToyotaAuth()
    auth._refresh_token = load_fixture("token_response")["refresh_token"]
    auth._access_token = "old"
    auth._expires_at = 0.0

    await auth.refresh()

    assert auth._access_token == "new_access_token"
    assert auth._expires_at > time.monotonic()


def test_ensure_valid_token_refreshes_when_expired():
    """ensure_valid_token returns False when token is expired."""
    auth = ToyotaAuth()
    auth._access_token = "x"
    auth._expires_at = time.monotonic() - 400  # past buffer
    assert auth.ensure_valid_token() is False


def test_ensure_valid_token_noop_when_valid():
    """ensure_valid_token returns True when token is still valid."""
    auth = ToyotaAuth()
    auth._access_token = "x"
    auth._expires_at = time.monotonic() + 600
    assert auth.ensure_valid_token() is True


@respx.mock
async def test_get_valid_access_token_refreshes_when_expired(load_fixture):
    """get_valid_access_token refreshes and returns new token when expired."""
    token_url = _auth_token_url()
    token_data = load_fixture("token_response")
    token_data["access_token"] = "refreshed_token"
    respx.post(token_url).mock(return_value=httpx.Response(200, json=token_data))

    auth = ToyotaAuth()
    auth._access_token = "old"
    auth._refresh_token = token_data["refresh_token"]
    auth._expires_at = time.monotonic() - 400

    out = await auth.get_valid_access_token()
    assert out == "refreshed_token"


async def test_get_valid_access_token_raises_when_not_logged_in():
    """get_valid_access_token raises when no access token."""
    auth = ToyotaAuth()
    with pytest.raises(RuntimeError, match="Not logged in"):
        await auth.get_valid_access_token()


def test_set_guid():
    """set_guid updates stored guid."""
    auth = ToyotaAuth()
    auth.set_guid("custom-guid")
    assert auth.guid == "custom-guid"


@respx.mock
async def test_logout():
    """logout revokes tokens and clears state."""
    revoke_url = _auth_revoke_url()
    respx.post(revoke_url).mock(return_value=httpx.Response(200))

    auth = ToyotaAuth()
    auth._access_token = "at"
    auth._refresh_token = "rt"
    auth._guid = "g"

    await auth.logout()

    assert auth._access_token is None
    assert auth._refresh_token is None
    assert auth._guid is None
    assert respx.post(revoke_url).call_count == 2  # both access and refresh tokens


@respx.mock
async def test_logout_noop_when_no_tokens():
    """logout does nothing when already logged out."""
    auth = ToyotaAuth()
    await auth.logout()
    # No requests made
    assert not respx.calls
