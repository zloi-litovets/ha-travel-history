"""Calendar of flights for Travel History."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import TravelHistoryError
from .const import DOMAIN
from .coordinator import (
    Flight,
    TravelHistoryConfigEntry,
    TravelHistoryCoordinator,
    arrival_time,
    departure_time,
    flight_route,
)
from .entity import TravelHistoryEntity

# The API filters by departure time; reach back far enough to also catch a
# long-haul flight that departed before the requested window but overlaps it.
_LONGEST_FLIGHT = timedelta(days=1)


def _to_event(flight: Flight) -> CalendarEvent:
    departure = flight["departure"]["airport"]
    arrival = flight["arrival"]["airport"]
    details = [
        f"{departure['name']} ({departure['city']}) → {arrival['name']} ({arrival['city']})",
        flight["airline"]["name"],
        flight["aircraft"]["name"],
    ]
    if flight["seat"]:
        details.append(flight["seat"])
    return CalendarEvent(
        start=departure_time(flight),
        end=arrival_time(flight),
        summary=f"{flight['flight_number']} {flight_route(flight)}",
        description="\n".join(details),
        location=departure["name"],
        uid=f"{DOMAIN}-{flight['id']}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TravelHistoryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FlightsCalendar(entry.runtime_data)])


class FlightsCalendar(TravelHistoryEntity, CalendarEntity):
    _attr_translation_key = "flights"

    def __init__(self, coordinator: TravelHistoryCoordinator) -> None:
        super().__init__(coordinator, "flights")

    @property
    def event(self) -> CalendarEvent | None:
        flight = self.coordinator.next_flight()
        return _to_event(flight) if flight else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        try:
            flights = await self.coordinator.client.flights(start_date - _LONGEST_FLIGHT, end_date)
        except TravelHistoryError as err:
            raise HomeAssistantError(f"Error fetching flights: {err}") from err
        events = [_to_event(flight) for flight in flights]
        return [event for event in events if event.end > start_date and event.start < end_date]
