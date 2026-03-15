"""Async Toyota Connected Europe API client."""

import hmac
import hashlib
import logging
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)

from toyota_api.auth import ToyotaAuth
from toyota_api.const import (
    API_BASE_URL,
    API_KEY,
    DEFAULT_APP_VERSION,
    DEFAULT_BRAND,
    DEFAULT_CHANNEL,
    DEFAULT_REGION,
)
from toyota_api.models import (
    AccountResponse,
    LocationResponse,
    NextMaintenanceResponse,
    ServiceHistoryResponse,
    TelemetryResponse,
    Vehicle,
    VehicleHealthResponse,
    VehiclesResponse,
)


def _x_client_ref(guid: str, version: str) -> str:
    """HMAC-SHA256(key=version, message=guid) as lowercase hex (matches Toyota One app)."""
    digest = hmac.new(
        version.encode("utf-8"), guid.encode("utf-8"), hashlib.sha256
    ).digest()
    return digest.hex()


class ToyotaClient:
    """Async client for Toyota OneAPI. Creates auth internally; pass username and password."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        base_url: str = API_BASE_URL,
        api_key: str = API_KEY,
        region: str = DEFAULT_REGION,
        brand: str = DEFAULT_BRAND,
        app_version: str = DEFAULT_APP_VERSION,
        channel: str = DEFAULT_CHANNEL,
    ) -> None:
        self._auth = ToyotaAuth()
        self._username = username
        self._password = password
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._region = region
        self._brand = brand
        self._app_version = app_version
        self._channel = channel
        self._generation_by_vin: dict[str, str] = {}
        self._guid: str | None = None

    async def login(self) -> None:
        """Log in with the credentials passed to the constructor."""
        await self._auth.login(self._username, self._password)

    async def logout(self) -> None:
        """Revoke token and clear session."""
        await self._auth.logout()

    def _default_headers(self, guid: str | None = None) -> dict[str, str]:
        x_client_ref = _x_client_ref(guid or "", self._app_version)
        return {
            "x-api-key": self._api_key,
            "api_key": self._api_key,
            "x-region": self._region,
            "region": self._region,
            "x-brand": self._brand,
            "brand": self._brand,
            "x-appversion": self._app_version,
            "x-channel": self._channel,
            "x-client-ref": x_client_ref,
            "accept": "application/json",
            "user-agent": "okhttp/4.12.0",
        }

    def _vehicle_headers(self, vin: str, guid: str | None = None) -> dict[str, str]:
        """Headers that require auth + vin. Generation from cache if available."""
        h = self._default_headers(guid=guid)
        h["vin"] = vin
        g = self._generation_by_vin.get(vin)
        if g:
            h["x-generation"] = g
            h["generation"] = g
        if self._auth.guid:
            h["x-guid"] = self._auth.guid
            h["guid"] = self._auth.guid
        return h

    async def _request(
        self,
        method: str,
        path: str,
        *,
        vin: str | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Send request with valid token and optional vehicle headers. Logs in lazily if needed."""
        try:
            token = await self._auth.get_valid_access_token()
        except RuntimeError:
            await self._auth.login(self._username, self._password)
            token = await self._auth.get_valid_access_token()
        guid = self._auth.guid
        headers = {**self._default_headers(guid=guid), "authorization": f"Bearer {token}"}
        if self._auth.guid:
            headers["x-guid"] = self._auth.guid
            headers["guid"] = self._auth.guid
        if vin:
            if vin not in self._generation_by_vin:
                await self.get_vehicles()
            headers["vin"] = vin
            g = self._generation_by_vin.get(vin)
            if g:
                headers["x-generation"] = g
                headers["generation"] = g

        async with httpx.AsyncClient(timeout=60.0, http2=True) as client:
            r = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
                json=json,
            )
            if not r.is_success:
                try:
                    body = r.text[:1000] if r.text else "(empty)"
                except Exception:
                    body = "(could not read)"
                logger.warning(
                    "API %s %s -> %s\nResponse: %s",
                    method,
                    path,
                    r.status_code,
                    body,
                )
            return r

    async def get_account(self) -> AccountResponse:
        """GET /v4/account - user profile."""
        r = await self._request("GET", "/v4/account")
        r.raise_for_status()
        data = r.json()
        payload = data.get("payload") or {}
        if payload.get("customer") and payload["customer"].get("guid"):
            self._guid = payload["customer"]["guid"]
            self._auth.set_guid(self._guid)
        return AccountResponse.model_validate(data)

    async def get_vehicles(self) -> list[Vehicle]:
        """GET /v2/vehicle/guid - list of vehicles. Caches generation per VIN and guid."""
        r = await self._request("GET", "/v2/vehicle/guid")
        r.raise_for_status()
        data = r.json()
        resp = VehiclesResponse.model_validate(data)
        for v in resp.payload or []:
            if v.vin and v.generation:
                self._generation_by_vin[v.vin] = v.generation
            if v.subscriberGuid and not self._guid:
                self._guid = v.subscriberGuid
                self._auth.set_guid(self._guid)
        return resp.payload or []

    async def get_location(self, vin: str) -> LocationResponse:
        """GET /v1/location - last parked position."""
        r = await self._request("GET", "/v1/location", vin=vin)
        r.raise_for_status()
        return LocationResponse.model_validate(r.json())

    async def get_trips(
        self,
        vin: str,
        from_date: date | str,
        to_date: date | str,
        *,
        route: bool = True,
        summary: bool = True,
        limit: int = 5,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /v1/trips - paginated trip history."""
        from_str = from_date.isoformat() if isinstance(from_date, date) else from_date
        to_str = to_date.isoformat() if isinstance(to_date, date) else to_date
        params = {
            "from": from_str,
            "to": to_str,
            "route": str(route).lower(),
            "summary": str(summary).lower(),
            "limit": limit,
            "offset": offset,
        }
        r = await self._request("GET", "/v1/trips", vin=vin, params=params)
        r.raise_for_status()
        return r.json()

    async def get_service_history(self, vin: str) -> ServiceHistoryResponse:
        """GET /v1/servicehistory/vehicle/summary - service history."""
        r = await self._request("GET", "/v1/servicehistory/vehicle/summary", vin=vin)
        r.raise_for_status()
        return ServiceHistoryResponse.model_validate(r.json())

    async def get_next_maintenance(self, vin: str) -> NextMaintenanceResponse:
        """GET /v1/osb/card - next maintenance due and schedule intervals."""
        r = await self._request("GET", "/v1/osb/card", vin=vin, params={"vin": vin})
        r.raise_for_status()
        return NextMaintenanceResponse.model_validate(r.json())

    async def get_telemetry(self, vin: str) -> TelemetryResponse:
        """GET /v3/telemetry - odometer, fuel level, timestamp."""
        r = await self._request("GET", "/v3/telemetry", vin=vin)
        r.raise_for_status()
        return TelemetryResponse.model_validate(r.json())

    async def get_vehicle_health(self, vin: str) -> VehicleHealthResponse:
        """GET /v1/vehiclehealth/status - warning lights, engine oil status."""
        r = await self._request("GET", "/v1/vehiclehealth/status", vin=vin)
        r.raise_for_status()
        return VehicleHealthResponse.model_validate(r.json())
