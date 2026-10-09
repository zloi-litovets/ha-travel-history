"""Polling coordinator for Travel History."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    TravelHistoryAuthError,
    TravelHistoryClient,
    TravelHistoryError,
    TravelHistoryNotFoundError,
)
from .const import (
    DOMAIN,
    EVENT_FLIGHT_CHANGE,
    EVENTS_MAX_PAGES,
    EVENTS_PAGE_SIZE,
    LANDED_GRACE,
    LOGGER,
    PHASE_CANCELLED,
    PHASE_IN_AIR,
    PHASE_LANDED,
    PHASE_NONE,
    PHASE_UPCOMING,
    SCAN_INTERVAL,
    UPCOMING_LIMIT,
)

type TravelHistoryConfigEntry = ConfigEntry[TravelHistoryCoordinator]
type Flight = dict[str, Any]


def departure_time(flight: Flight) -> datetime | None:
    """Scheduled (recorded) departure."""
    return dt_util.parse_datetime(flight["departure"]["time"])


def arrival_time(flight: Flight) -> datetime | None:
    """Scheduled (recorded) arrival."""
    return dt_util.parse_datetime(flight["arrival"]["time"])


def flight_live(flight: Flight | None) -> dict[str, Any] | None:
    """The live-tracking block, or None (not tracked yet, tracking off, or
    a server without live tracking).
    """
    return flight.get("live") if flight else None


def _parse(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


def live_time(end: dict[str, Any] | None) -> datetime | None:
    """Best live time for one end: actual, else estimated."""
    if not end:
        return None
    return _parse(end.get("actual")) or _parse(end.get("estimated"))


def expected_departure(flight: Flight) -> datetime | None:
    """When the flight leaves (or left) according to live tracking: takeoff,
    gate departure or estimate - falling back to the schedule.
    """
    live = flight_live(flight)
    if live:
        end = live["departure"]
        moment = _parse(end.get("runway")) or live_time(end)
        if moment is not None:
            return moment
    return departure_time(flight)


def expected_arrival(flight: Flight) -> datetime | None:
    """Same for arrival: touchdown, gate arrival or estimate."""
    live = flight_live(flight)
    if live:
        end = live["arrival"]
        moment = _parse(end.get("runway")) or live_time(end)
        if moment is not None:
            return moment
    return arrival_time(flight)


def flight_phase(flight: Flight | None, now: datetime) -> str:
    """Computed locally rather than taken from the server's `phase`, so it
    stays right between polls. Uses live times when the flight is tracked,
    so a delay keeps it `upcoming` / `in_air` for as long as it lasts.
    """
    if flight is None:
        return PHASE_NONE
    live = flight_live(flight)
    if live and live.get("cancelled"):
        return PHASE_CANCELLED
    if now < expected_departure(flight):
        return PHASE_UPCOMING
    if now < expected_arrival(flight):
        return PHASE_IN_AIR
    return PHASE_LANDED


def airport_code(flight: Flight, end: str) -> str:
    airport = flight[end]["airport"]
    return airport["iata"] or airport["icao"]


def flight_route(flight: Flight) -> str:
    return f"{airport_code(flight, 'departure')} → {airport_code(flight, 'arrival')}"


@dataclass
class TravelHistoryData:
    upcoming: list[Flight]
    stats: dict[str, Any]

    def next_flight(self, now: datetime, landed_grace: timedelta = LANDED_GRACE) -> Flight | None:
        """The flight in the air right now, or the next one to depart.
        A flight that landed less than `landed_grace` ago is kept (phase
        `landed`) until the following flight departs.
        """
        landed: Flight | None = None
        for flight in self.upcoming:
            if expected_arrival(flight) > now:
                if landed is not None and now < expected_departure(flight):
                    return landed
                return flight
            if expected_arrival(flight) + landed_grace > now:
                landed = flight
        return landed


class TravelHistoryCoordinator(DataUpdateCoordinator[TravelHistoryData]):
    config_entry: TravelHistoryConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: TravelHistoryConfigEntry, client: TravelHistoryClient
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        # Live-tracking changes are fired as HA events from the moment the
        # integration starts - nothing older is replayed on a restart.
        self._events_since: datetime | None = None
        self._last_event_id: int | None = None
        self._events_supported = True

    async def _async_update_data(self) -> TravelHistoryData:
        try:
            upcoming = await self.client.upcoming_flights(UPCOMING_LIMIT)
            stats = await self.client.stats()
        except TravelHistoryAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TravelHistoryError as err:
            raise UpdateFailed(f"Error fetching flights: {err}") from err
        await self._fire_new_tracking_events()
        return TravelHistoryData(upcoming=upcoming, stats=stats)

    async def _fire_new_tracking_events(self) -> None:
        if not self._events_supported:
            return
        if self._events_since is None:
            # First refresh: only remember where "new" starts.
            self._events_since = dt_util.utcnow()
            return

        events: list[dict[str, Any]] = []
        try:
            for _ in range(EVENTS_MAX_PAGES):
                page = await self.client.tracking_events(
                    after_id=self._last_event_id,
                    since=self._events_since if self._last_event_id is None else None,
                    limit=EVENTS_PAGE_SIZE,
                )
                events += page
                if page:
                    self._last_event_id = page[-1]["id"]
                if len(page) < EVENTS_PAGE_SIZE:
                    break
        except TravelHistoryNotFoundError:
            LOGGER.debug("Server has no live tracking events endpoint, not polling it")
            self._events_supported = False
        except TravelHistoryError as err:
            # Flights and stats are fine - don't mark everything unavailable
            # over the events feed; the next poll picks up where this left off.
            LOGGER.warning("Error fetching live tracking events: %s", err)

        for event in events:
            self.hass.bus.async_fire(
                EVENT_FLIGHT_CHANGE, {"entry_id": self.config_entry.entry_id, **event}
            )

    def next_flight(self, landed_grace: timedelta = LANDED_GRACE) -> Flight | None:
        return self.data.next_flight(dt_util.utcnow(), landed_grace)
