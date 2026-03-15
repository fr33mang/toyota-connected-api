"""ForgeRock AM + OAuth2 PKCE authentication for Toyota Connected Europe."""

import base64
import hashlib
import json as _json
import logging
import re
import secrets
import time
from base64 import urlsafe_b64encode
from urllib.parse import urlencode
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _log_response(r: httpx.Response, label: str = "") -> None:
    """Log response status, headers, and body (for debugging)."""
    try:
        body = r.text[:2000] if r.text else "(empty)"
        if len(r.text or "") > 2000:
            body += "...[truncated]"
    except Exception:
        body = "(could not read body)"
    logger.debug(
        "%s %s %s\nResponse headers: %s\nResponse body: %s",
        label,
        r.request.method,
        r.request.url,
        dict(r.headers),
        body,
    )
    if not r.is_success:
        logger.warning("%s %s %s -> %s %s", label, r.request.method, r.request.url, r.status_code, body[:500])

from toyota_api.const import (
    AUTH_BASE_URL,
    AUTH_INDEX_SERVICE,
    CLIENT_ID,
    CLIENT_SECRET,
    JSON_REALM_PATH,
    OAUTH_REALM_PATH,
    REDIRECT_URI,
    SCOPE,
    TOKEN_EXPIRY_BUFFER_SECONDS,
)


def _pkce_code_verifier() -> str:
    """Generate a PKCE code_verifier (43–128 chars, unreserved)."""
    return secrets.token_urlsafe(32)


def _pkce_code_challenge(verifier: str) -> str:
    """S256 code challenge: base64url(sha256(verifier))."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _guid_from_jwt(access_token: str) -> str | None:
    """Extract 'sub' (user guid) from JWT access_token. No signature verification."""
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64)
        data = _json.loads(payload)
        return data.get("sub")
    except Exception:
        return None


def _fill_callbacks(callbacks: list[dict], inputs: dict[str, Any]) -> list[dict]:
    """Set input values on callbacks by input name (e.g. IDToken1, IDToken2)."""
    out = []
    for cb in callbacks:
        cb = {**cb}
        if "input" in cb and isinstance(cb["input"], list):
            new_inputs = []
            for inp in cb["input"]:
                inp = dict(inp) if isinstance(inp, dict) else {}
                name = inp.get("name")
                if name and name in inputs:
                    inp["value"] = inputs[name]
                new_inputs.append(inp)
            cb["input"] = new_inputs
        out.append(cb)
    return out


class ToyotaAuth:
    """Async Toyota Connected Europe auth: ForgeRock callbacks + OAuth2 PKCE + token refresh."""

    def __init__(
        self,
        *,
        auth_base_url: str = AUTH_BASE_URL,
        client_id: str = CLIENT_ID,
        client_secret: str = CLIENT_SECRET,
        redirect_uri: str = REDIRECT_URI,
        scope: str = SCOPE,
    ) -> None:
        self.auth_base_url = auth_base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scope = scope
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._guid: str | None = None

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def guid(self) -> str | None:
        return self._guid

    def _token_url(self) -> str:
        return f"{self.auth_base_url}{OAUTH_REALM_PATH}/access_token"

    def _authenticate_url(self) -> str:
        return (
            f"{self.auth_base_url}{JSON_REALM_PATH}/authenticate"
            f"?authIndexType=service&authIndexValue={AUTH_INDEX_SERVICE}"
        )

    def _authorize_url(self, code_challenge: str) -> str:
        params = {
            "client_id": self.client_id,
            "scope": self.scope,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.auth_base_url}{OAUTH_REALM_PATH}/authorize?{urlencode(params)}"

    async def login(self, username: str, password: str) -> None:
        """Perform full login: ForgeRock callbacks then OAuth2 code exchange."""
        code_verifier = _pkce_code_verifier()
        code_challenge = _pkce_code_challenge(code_verifier)

        auth_origin = f"{self.auth_base_url}"
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=False,
            http2=True,
            headers={
                "accept-api-version": "resource=2.1, protocol=1.0",
                "content-type": "application/json; charset=utf-8",
                "x-brand": "T",
                "user-agent": "okhttp/4.12.0",
                "accept-language": "en-GB,en;q=0.9",
                "origin": auth_origin,
                "referer": auth_origin + "/",
            },
        ) as client:
            # Step 1: POST authenticate (empty) → locale callbacks
            body: dict[str, Any] = {}
            password_sent = False
            for step in range(10):  # max steps
                r = await client.post(self._authenticate_url(), json=body)
                _log_response(r, f"[auth step {step}]")
                r.raise_for_status()
                data = r.json()

                if data.get("tokenId"):
                    # Session established; proceed to authorize
                    break

                # ForgeRock can return failure info
                if data.get("failedId") or data.get("reason"):
                    raise RuntimeError(
                        f"Login failed: {data.get('reason') or data.get('failedId') or 'unknown'}"
                    )

                auth_id = data.get("authId")
                callbacks = data.get("callbacks") or []

                if not callbacks:
                    raise RuntimeError("No callbacks in ForgeRock response")

                # Decide what to send based on callback prompts
                prompts = []
                for cb in callbacks:
                    for o in cb.get("output", []) or []:
                        if isinstance(o, dict) and "value" in o:
                            prompts.append(o["value"])

                if "Market Locale" in prompts or "Internationalization" in prompts:
                    # Locale step: send default locale
                    body = {
                        "authId": auth_id,
                        "callbacks": _fill_callbacks(
                            callbacks,
                            {"IDToken1": "GB", "IDToken2": "en-GB", "IDToken3": "en"},
                        ),
                    }
                elif "User Name" in prompts:
                    # Username + auth method (Local = 0)
                    body = {
                        "authId": auth_id,
                        "callbacks": _fill_callbacks(
                            callbacks,
                            {"IDToken1": username, "IDToken2": 0},
                        ),
                    }
                elif "Password" in prompts:
                    if password_sent:
                        raise RuntimeError("Invalid username or password")
                    password_sent = True
                    body = {
                        "authId": auth_id,
                        "callbacks": _fill_callbacks(
                            callbacks,
                            {"IDToken1": password, "IDToken2": 0},
                        ),
                    }
                else:
                    raise RuntimeError(f"Unknown ForgeRock callbacks: {prompts}")
            else:
                # Include last response so we can see what the server actually returned
                last_prompts = []
                for cb in (data.get("callbacks") or []):
                    for o in cb.get("output", []) or []:
                        if isinstance(o, dict) and "value" in o:
                            last_prompts.append(o["value"])
                raise RuntimeError(
                    "ForgeRock auth did not complete with tokenId. "
                    f"Last response prompts: {last_prompts}. "
                    "Full keys: " + str(list(data.keys()))
                )

            # GET authorize (session cookie is in client jar)
            authz_url = self._authorize_url(code_challenge)
            r = await client.get(authz_url)
            _log_response(r, "[authorize]")
            if r.status_code != 302:
                raise RuntimeError(f"Expected 302 from authorize, got {r.status_code}")
            location = r.headers.get("location") or ""
            code_match = re.search(r"[?&]code=([^&]+)", location)
            if not code_match:
                raise RuntimeError(f"No code in redirect: {location}")
            code = code_match.group(1)

            # POST access_token
            token_r = await client.post(
                self._token_url(),
                data={
                    "client_id": self.client_id,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={
                    "authorization": f"Basic {_basic_auth(self.client_id, self.client_secret)}",
                    "content-type": "application/x-www-form-urlencoded",
                    "accept-api-version": "resource=2.1, protocol=1.0",
                },
            )
            _log_response(token_r, "[access_token]")
            token_r.raise_for_status()
            token_data = token_r.json()

        self._access_token = token_data["access_token"]
        self._refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in", 3600))
        self._expires_at = time.monotonic() + expires_in
        # guid = user UUID from JWT "sub" claim (required by API on first request)
        self._guid = _guid_from_jwt(self._access_token)

    async def refresh(self) -> None:
        """Refresh access token using refresh_token (inferred OAuth2 flow)."""
        if not self._refresh_token:
            raise RuntimeError("No refresh token; login first")
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                self._token_url(),
                data={
                    "client_id": self.client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                headers={
                    "authorization": f"Basic {_basic_auth(self.client_id, self.client_secret)}",
                    "content-type": "application/x-www-form-urlencoded",
                    "accept-api-version": "resource=2.1, protocol=1.0",
                },
            )
            r.raise_for_status()
            data = r.json()
        self._access_token = data["access_token"]
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._expires_at = time.monotonic() + expires_in
        if not self._guid:
            self._guid = _guid_from_jwt(self._access_token)

    def ensure_valid_token(self) -> bool:
        """Return True if access_token is set and not expired (call refresh from caller if needed)."""
        if not self._access_token:
            return False
        if self._expires_at - TOKEN_EXPIRY_BUFFER_SECONDS <= time.monotonic():
            return False
        return True

    async def get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if not self._access_token:
            raise RuntimeError("Not logged in")
        if not self.ensure_valid_token() and self._refresh_token:
            await self.refresh()
        if not self._access_token:
            raise RuntimeError("Not logged in")
        return self._access_token

    def set_guid(self, guid: str) -> None:
        """Set user GUID (from account/vehicles response)."""
        self._guid = guid

    async def logout(self) -> None:
        """Revoke token and clear state. Toyota API /v1/logout is optional (needs token)."""
        if not self._access_token and not self._refresh_token:
            return
        async with httpx.AsyncClient(timeout=15.0) as client:
            if self._access_token:
                try:
                    await client.post(
                        f"{self.auth_base_url}{OAUTH_REALM_PATH}/token/revoke",
                        data={"token": self._access_token, "client_id": self.client_id},
                        headers={
                            "authorization": f"Basic {_basic_auth(self.client_id, self.client_secret)}",
                            "content-type": "application/x-www-form-urlencoded",
                        },
                    )
                except Exception:
                    pass
            if self._refresh_token:
                try:
                    await client.post(
                        f"{self.auth_base_url}{OAUTH_REALM_PATH}/token/revoke",
                        data={"token": self._refresh_token, "client_id": self.client_id},
                        headers={
                            "authorization": f"Basic {_basic_auth(self.client_id, self.client_secret)}",
                            "content-type": "application/x-www-form-urlencoded",
                        },
                    )
                except Exception:
                    pass
        self._access_token = None
        self._refresh_token = None
        self._expires_at = 0.0
        self._guid = None


def _basic_auth(username: str, password: str) -> str:
    import base64
    return base64.b64encode(f"{username}:{password}".encode()).decode()
