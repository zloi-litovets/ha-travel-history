"""Setup, entity and calendar tests."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.travel_history.const import SCAN_INTERVAL

from .conftest import API, STATS, make_flight


async def _setup(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_entities(hass: HomeAssistant, config_entry, mock_api, upcoming) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    next_flight = hass.states.get("sensor.fly_example_com_next_flight")
    assert next_flight.state == "PS101"
    assert next_flight.attributes["route"] == "KBP → AMS"
    assert next_flight.attributes["seat"] == "12A"
    assert next_flight.attributes["departure_iata"] == "KBP"
    assert next_flight.attributes["arrival_iata"] == "AMS"
    assert next_flight.attributes["arrival_country"] == "-"

    departure = hass.states.get("sensor.fly_example_com_next_flight_departure")
    expected = dt_util.parse_datetime(upcoming[0]["departure"]["time"]).replace(microsecond=0)
    assert dt_util.parse_datetime(departure.state) == expected

    assert hass.states.get("sensor.fly_example_com_next_flight_phase").state == "upcoming"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_OFF
    assert hass.states.get("sensor.fly_example_com_total_flights").state == "214"
    assert hass.states.get("sensor.fly_example_com_total_distance").state == "412345"
    assert hass.states.get("sensor.fly_example_com_upcoming_flights").state == "2"

    calendar = hass.states.get("calendar.fly_example_com_flights")
    assert calendar.attributes["message"] == "PS101 KBP → AMS"

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_in_flight_and_skips_landed(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    now = dt_util.utcnow()
    flights = [
        # Landed 20 min ago - still in the server's upcoming list (grace period).
        make_flight(1, now - timedelta(hours=3, minutes=20)),
        make_flight(2, now - timedelta(hours=1)),
    ]
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": flights, "count": 2})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.fly_example_com_next_flight").state == "PS2"
    assert hass.states.get("sensor.fly_example_com_next_flight_phase").state == "in_air"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_ON
    assert hass.states.get("calendar.fly_example_com_flights").state == STATE_ON


async def test_keeps_just_landed_flight(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    now = dt_util.utcnow()
    flights = [
        # Landed 20 min ago, the next one departs in an hour.
        make_flight(1, now - timedelta(hours=3, minutes=20)),
        make_flight(2, now + timedelta(hours=1)),
    ]
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": flights, "count": 2})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.fly_example_com_next_flight").state == "PS1"
    assert hass.states.get("sensor.fly_example_com_next_flight_phase").state == "landed"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_OFF


async def test_drops_landed_flight_after_grace(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    now = dt_util.utcnow()
    flights = [
        make_flight(1, now - timedelta(hours=3, minutes=40)),
        make_flight(2, now + timedelta(hours=1)),
    ]
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": flights, "count": 2})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.fly_example_com_next_flight").state == "PS2"
    assert hass.states.get("sensor.fly_example_com_next_flight_phase").state == "upcoming"


async def test_airport_without_iata(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    flight = make_flight(1, dt_util.utcnow() + timedelta(days=1))
    flight["arrival"]["airport"]["iata"] = None
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": [flight], "count": 1})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    await _setup(hass, config_entry)

    attributes = hass.states.get("sensor.fly_example_com_next_flight").attributes
    assert attributes["arrival_iata"] is None
    assert attributes["route"] == "KBP → EHAM"


async def test_no_planned_flights(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": [], "count": 0})
    aioclient_mock.get(f"{API}stats/summary/", json={**STATS, "upcoming_flights": None})
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.fly_example_com_next_flight").state == STATE_UNKNOWN
    assert hass.states.get("sensor.fly_example_com_next_flight_departure").state == STATE_UNKNOWN
    assert hass.states.get("sensor.fly_example_com_next_flight_phase").state == "none"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_OFF
    assert hass.states.get("sensor.fly_example_com_upcoming_flights").state == STATE_UNKNOWN
    assert hass.states.get("calendar.fly_example_com_flights").state == STATE_OFF


async def test_auth_failure_on_setup_starts_reauth(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    aioclient_mock.get(f"{API}flights/upcoming/", status=HTTPStatus.UNAUTHORIZED)
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_server_down_on_setup_retries(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    aioclient_mock.get(f"{API}flights/upcoming/", status=HTTPStatus.BAD_GATEWAY)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_update_failure_marks_unavailable(
    hass: HomeAssistant, config_entry, mock_api, aioclient_mock, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}flights/upcoming/", status=HTTPStatus.BAD_GATEWAY)

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.fly_example_com_next_flight").state == STATE_UNAVAILABLE


async def test_calendar_events(hass: HomeAssistant, config_entry, mock_api, aioclient_mock, hass_client) -> None:
    await _setup(hass, config_entry)
    now = dt_util.utcnow()
    flights = [
        # Departed before the window, still in the air inside it.
        make_flight(201, now - timedelta(hours=26), hours=13),
        make_flight(202, now + timedelta(days=1)),
        # Ended before the window - must be filtered out.
        make_flight(203, now - timedelta(hours=30), hours=2),
    ]
    aioclient_mock.get(f"{API}flights/", json={"flights": flights, "count": len(flights)})

    start = now - timedelta(hours=24)
    end = now + timedelta(days=7)
    client = await hass_client()
    resp = await client.get(
        "/api/calendars/calendar.fly_example_com_flights",
        params={"start": start.isoformat(), "end": end.isoformat()},
    )
    assert resp.status == HTTPStatus.OK
    events = await resp.json()
    assert [event["summary"] for event in events] == ["PS201 KBP → AMS", "PS202 KBP → AMS"]
    assert "Boryspil (Kyiv) → Schiphol (Amsterdam)" in events[1]["description"]

    # Asked the server for flights departing up to a day before the window.
    _, url, _, _ = aioclient_mock.mock_calls[-1]
    requested_from = dt_util.parse_datetime(url.query["from"])
    assert requested_from == start - timedelta(days=1)


async def test_diagnostics_redacts_token(hass: HomeAssistant, config_entry, mock_api, hass_client) -> None:
    await _setup(hass, config_entry)
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    assert diagnostics["entry"]["api_token"] == "**REDACTED**"
    assert diagnostics["data"]["stats"] == STATS
