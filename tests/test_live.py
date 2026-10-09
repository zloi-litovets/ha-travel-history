"""Live tracking: sensors, phases and change events."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.travel_history.const import EVENT_FLIGHT_CHANGE, SCAN_INTERVAL

from .conftest import API, STATS, make_flight, make_live

SENSOR = "sensor.fly_example_com_next_flight"


async def _setup(hass: HomeAssistant, config_entry, aioclient_mock, flights) -> None:
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": flights, "count": len(flights)})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_live_sensors(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    departure = dt_util.utcnow() + timedelta(hours=3)
    estimated = departure + timedelta(minutes=40)
    live = make_live(
        departure,
        status="delayed",
        departure={"estimated": estimated.isoformat(), "delay_minutes": 40, "gate": "D7"},
        arrival={"baggage_belt": "12", "terminal": "2"},
    )
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, departure, live=live)])

    assert hass.states.get(f"{SENSOR}_status").state == "delayed"
    expected = hass.states.get(f"{SENSOR}_expected_departure")
    assert dt_util.parse_datetime(expected.state) == estimated.replace(microsecond=0)
    assert expected.attributes["delay_minutes"] == 40
    assert expected.attributes["gate"] == "D7"
    assert hass.states.get(f"{SENSOR}_departure_delay").state == "40"
    gate = hass.states.get(f"{SENSOR}_gate")
    assert gate.state == "D7"
    assert gate.attributes["terminal"] == "D"
    belt = hass.states.get(f"{SENSOR}_baggage_belt")
    assert belt.state == "12"
    assert belt.attributes["terminal"] == "2"

    attributes = hass.states.get(SENSOR).attributes
    assert attributes["live_status"] == "delayed"
    assert attributes["departure_gate"] == "D7"
    assert attributes["baggage_belt"] == "12"
    assert attributes["live_registration"] == "PH-BXY"
    # Scheduled sensors stay on the recorded times.
    scheduled = hass.states.get(f"{SENSOR}_departure")
    assert dt_util.parse_datetime(scheduled.state) == departure.replace(microsecond=0)


async def test_untracked_flight_has_unknown_live_sensors(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, dt_util.utcnow() + timedelta(days=1))])

    for suffix in ("status", "expected_departure", "expected_arrival", "departure_delay", "gate", "baggage_belt"):
        assert hass.states.get(f"{SENSOR}_{suffix}").state == STATE_UNKNOWN, suffix
    attributes = hass.states.get(SENSOR).attributes
    assert attributes["live_status"] is None
    assert attributes["departure_gate"] is None


async def test_server_unknown_status_is_ha_unknown(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    departure = dt_util.utcnow() + timedelta(hours=3)
    live = make_live(departure, status="unknown")
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, departure, live=live)])
    assert hass.states.get(f"{SENSOR}_status").state == STATE_UNKNOWN


async def test_delay_keeps_flight_upcoming_past_schedule(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    now = dt_util.utcnow()
    departure = now - timedelta(minutes=30)  # scheduled half an hour ago
    live = make_live(departure, status="delayed",
                     departure={"estimated": (now + timedelta(hours=1)).isoformat()})
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, departure, live=live)])

    assert hass.states.get(f"{SENSOR}_phase").state == "upcoming"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_OFF


async def test_delayed_flight_stays_in_air_past_scheduled_arrival(
    hass: HomeAssistant, config_entry, aioclient_mock
) -> None:
    now = dt_util.utcnow()
    departure = now - timedelta(hours=4)  # scheduled to land an hour ago
    live = make_live(
        departure,
        status="en_route",
        departure={"actual": (departure + timedelta(hours=2)).isoformat(),
                   "runway": (departure + timedelta(hours=2, minutes=15)).isoformat()},
        arrival={"estimated": (now + timedelta(hours=1)).isoformat()},
    )
    flights = [make_flight(1, departure, live=live), make_flight(2, now + timedelta(days=2))]
    await _setup(hass, config_entry, aioclient_mock, flights)

    assert hass.states.get(SENSOR).state == "PS1"
    assert hass.states.get(f"{SENSOR}_phase").state == "in_air"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_ON


async def test_cancelled_flight(hass: HomeAssistant, config_entry, aioclient_mock) -> None:
    now = dt_util.utcnow()
    departure = now - timedelta(hours=1)
    live = make_live(departure, status="cancelled", cancelled=True, tracking="finalized")
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, departure, live=live)])

    assert hass.states.get(f"{SENSOR}_phase").state == "cancelled"
    assert hass.states.get(f"{SENSOR}_status").state == "cancelled"
    assert hass.states.get("binary_sensor.fly_example_com_in_flight").state == STATE_OFF


async def test_change_events_are_fired(
    hass: HomeAssistant, config_entry, mock_api, aioclient_mock, freezer: FrozenDateTimeFactory
) -> None:
    fired = async_capture_events(hass, EVENT_FLIGHT_CHANGE)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    # First refresh only marks the starting point - nothing old is replayed.
    assert not [call for call in aioclient_mock.mock_calls if "tracking/events" in str(call[1])]

    event = {
        "id": 57, "at": dt_util.utcnow().isoformat(), "kind": "gate", "field": "dep_gate",
        "old": None, "new": "D7", "flight_id": 101, "flight_number": "PS101",
    }
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": [], "count": 0})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    aioclient_mock.get(f"{API}tracking/events/", json={"events": [event], "count": 1})
    await _tick(hass, freezer)

    assert len(fired) == 1
    assert fired[0].data["kind"] == "gate"
    assert fired[0].data["new"] == "D7"
    assert fired[0].data["entry_id"] == config_entry.entry_id
    _, url, _, _ = aioclient_mock.mock_calls[-1]
    assert "since" in url.query and "after_id" not in url.query

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}flights/upcoming/", json={"flights": [], "count": 0})
    aioclient_mock.get(f"{API}stats/summary/", json=STATS)
    aioclient_mock.get(f"{API}tracking/events/", json={"events": [], "count": 0})
    await _tick(hass, freezer)

    assert len(fired) == 1
    _, url, _, _ = aioclient_mock.mock_calls[-1]
    assert url.query["after_id"] == "57"
    assert "since" not in url.query


async def test_events_endpoint_missing_on_old_server(
    hass: HomeAssistant, config_entry, aioclient_mock, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, dt_util.utcnow() + timedelta(days=1))])
    aioclient_mock.get(f"{API}tracking/events/", status=HTTPStatus.NOT_FOUND)
    await _tick(hass, freezer)
    assert hass.states.get(SENSOR).state == "PS1"

    calls = len(aioclient_mock.mock_calls)
    await _tick(hass, freezer)
    # Not asked again; flights and stats still are.
    new_urls = [str(call[1]) for call in aioclient_mock.mock_calls[calls:]]
    assert not [url for url in new_urls if "tracking/events" in url]
    assert any("flights/upcoming" in url for url in new_urls)


async def test_events_error_keeps_entities_available(
    hass: HomeAssistant, config_entry, aioclient_mock, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, config_entry, aioclient_mock, [make_flight(1, dt_util.utcnow() + timedelta(days=1))])
    aioclient_mock.get(f"{API}tracking/events/", status=HTTPStatus.BAD_GATEWAY)
    await _tick(hass, freezer)
    assert hass.states.get(SENSOR).state == "PS1"
