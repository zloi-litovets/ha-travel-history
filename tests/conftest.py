"""Fixtures for Travel History tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.util import dt as dt_util

from custom_components.travel_history.const import DOMAIN

URL = "https://fly.example.com"
API = f"{URL}/api/ext/v1/"
TOKEN = "trv_test-token"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_flight(flight_id: int, departure: datetime, hours: float = 3, **extra: Any) -> dict[str, Any]:
    arrival = departure + timedelta(hours=hours)

    def end(icao: str, iata: str, name: str, city: str, moment: datetime) -> dict[str, Any]:
        return {
            "airport": {"icao": icao, "iata": iata, "name": name, "city": city, "country": "-"},
            "time": moment.isoformat(),
            "local_time": moment.isoformat(),
            "timezone": "UTC",
        }

    return {
        "id": flight_id,
        "flight_number": f"PS{flight_id}",
        "phase": "upcoming",
        "is_future": True,
        "departs_in_seconds": 0,
        "duration_minutes": int(hours * 60),
        "distance_km": 1640,
        "departure": end("UKBB", "KBP", "Boryspil", "Kyiv", departure),
        "arrival": end("EHAM", "AMS", "Schiphol", "Amsterdam", arrival),
        "airline": {"name": "KLM", "iata": "KL", "icao": "KLM"},
        "aircraft": {"code": "B738", "name": "Boeing 737-800", "registration": None},
        "ticket_class": "Economy",
        "seat": "12A",
        "diversion": None,
        "live": None,
        **extra,
    }


STATS = {
    "flights": 214,
    "distance_km": 412345,
    "hours": 610.5,
    "airports": 63,
    "countries": 27,
    "airlines": 31,
    "aircraft_types": 22,
    "upcoming_flights": 2,
}


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="fly.example.com",
        unique_id=URL,
        data={CONF_URL: URL, CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: True},
    )


@pytest.fixture
def upcoming() -> list[dict[str, Any]]:
    now = dt_util.utcnow()
    return [
        make_flight(101, now + timedelta(days=2)),
        make_flight(102, now + timedelta(days=10)),
    ]


@pytest.fixture
def mock_api(aioclient_mock, upcoming):
    aioclient_mock.get(f"{API}whoami/", json={"token": {"name": "HA"}, "can_see_future_flights": True})
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": upcoming, "count": len(upcoming)})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    return aioclient_mock
