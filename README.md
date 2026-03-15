# Toyota Connected Europe API Client

[![Lint](https://github.com/fr33mang/toyota-connected-api/actions/workflows/lint.yml/badge.svg)](https://github.com/fr33mang/toyota-connected-api/actions/workflows/lint.yml)
[![Tests](https://github.com/fr33mang/toyota-connected-api/actions/workflows/test.yml/badge.svg)](https://github.com/fr33mang/toyota-connected-api/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/fr33mang/toyota-connected-api/branch/main/graph/badge.svg)](https://codecov.io/gh/fr33mang/toyota-connected-api)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Unofficial.** This project is not affiliated with, endorsed by, or connected to Toyota. Use at your own risk.

Async Python client for the My Toyota (Toyota Connected Europe) API, reverse-engineered from HAR traffic.

## Setup

Use a virtual environment (required on many systems; avoids “externally-managed-environment” errors):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install .
```

For development (editable install with Black and pre-commit):

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install   # optional: run Black on commit
```

As a dependency from GitHub (e.g. for a Home Assistant custom integration):

```bash
pip install toyota-connected-api @ git+https://github.com/fr33mang/toyota-connected-api@main
```

## Usage

```python
import asyncio
from toyota_api import ToyotaClient

async def main():
    client = ToyotaClient("your@email.com", "password")
    vehicles = await client.get_vehicles()  # logs in automatically
    # ...
    await client.logout()

asyncio.run(main())
```

## Implemented endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `get_account()` | `GET /v4/account` | User profile: name, contacts, addresses, language, country. |
| `get_vehicles()` | `GET /v2/vehicle/guid` | List of linked vehicles (VIN, model, year, generation, fuel type, etc.). Fills the generation cache used by other vehicle endpoints. |
| `get_location(vin)` | `GET /v1/location` | Last parked position: coordinates and timestamp. |
| `get_trips(vin, from_date, to_date, ...)` | `GET /v1/trips` | Trip history for a date range; optional route, summary, pagination (limit/offset). |
| `get_service_history(vin)` | `GET /v1/servicehistory/vehicle/summary` | Service history: dates, mileage, provider, category. |
| `get_next_maintenance(vin)` | `GET /v1/osb/card` | Next maintenance due date and schedule intervals (time/mileage). |
| `get_telemetry(vin)` | `GET /v3/telemetry` | Live-ish data: odometer, fuel level (%), last update time. |
| `get_vehicle_health(vin)` | `GET /v1/vehiclehealth/status` | Warning lights and indicators (e.g. engine oil). |

Vehicle methods take only `vin`; the client loads the vehicle list when needed to resolve generation. `login()` and `logout()` are available on the client for explicit session control; the first API call will log in automatically if not already authenticated.