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

from .api import TravelHistoryAuthError, TravelHistoryClient, TravelHistoryError
from .const import (
    DOMAIN,
    LANDED_GRACE,
    LOGGER,
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
    return dt_util.parse_datetime(flight["departure"]["time"])


def arrival_time(flight: Flight) -> datetime | None:
    return dt_util.parse_datetime(flight["arrival"]["time"])


def flight_phase(flight: Flight | None, now: datetime) -> str:
    """Computed locally rather than taken from the server's `phase`, so it
    stays right between polls.
    """
    if flight is None:
        return PHASE_NONE
    if now < departure_time(flight):
        return PHASE_UPCOMING
    if now < arrival_time(flight):
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
            if arrival_time(flight) > now:
                if landed is not None and now < departure_time(flight):
                    return landed
                return flight
            if arrival_time(flight) + landed_grace > now:
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

    async def _async_update_data(self) -> TravelHistoryData:
        try:
            upcoming = await self.client.upcoming_flights(UPCOMING_LIMIT)
            stats = await self.client.stats()
        except TravelHistoryAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TravelHistoryError as err:
            raise UpdateFailed(f"Error fetching flights: {err}") from err
        return TravelHistoryData(upcoming=upcoming, stats=stats)

    def next_flight(self, landed_grace: timedelta = LANDED_GRACE) -> Flight | None:
        return self.data.next_flight(dt_util.utcnow(), landed_grace)
