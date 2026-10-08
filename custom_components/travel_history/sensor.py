"""Sensors for Travel History."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import PHASES
from .coordinator import (
    Flight,
    TravelHistoryConfigEntry,
    TravelHistoryCoordinator,
    arrival_time,
    departure_time,
    flight_phase,
    flight_route,
)
from .entity import TravelHistoryEntity


def _next_flight_attributes(flight: Flight | None) -> dict[str, Any]:
    if flight is None:
        return {}
    return {
        "route": flight_route(flight),
        "airline": flight["airline"]["name"],
        "aircraft": flight["aircraft"]["name"],
        "registration": flight["aircraft"]["registration"],
        "ticket_class": flight["ticket_class"],
        "seat": flight["seat"],
        # Real IATA only (null when the airport has none); `route` falls back
        # to ICAO for display.
        "departure_iata": flight["departure"]["airport"]["iata"],
        "departure_airport": flight["departure"]["airport"]["name"],
        "departure_city": flight["departure"]["airport"]["city"],
        "departure_country": flight["departure"]["airport"]["country"],
        "departure_local_time": flight["departure"]["local_time"],
        "arrival_iata": flight["arrival"]["airport"]["iata"],
        "arrival_airport": flight["arrival"]["airport"]["name"],
        "arrival_city": flight["arrival"]["airport"]["city"],
        "arrival_country": flight["arrival"]["airport"]["country"],
        "arrival_local_time": flight["arrival"]["local_time"],
        "duration_minutes": flight["duration_minutes"],
        "distance_km": flight["distance_km"],
    }


@dataclass(frozen=True, kw_only=True)
class NextFlightSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Flight | None, datetime], StateType | datetime]
    attributes_fn: Callable[[Flight | None], dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class StatsSensorDescription(SensorEntityDescription):
    stat_key: str


NEXT_FLIGHT_SENSORS: tuple[NextFlightSensorDescription, ...] = (
    NextFlightSensorDescription(
        key="next_flight",
        translation_key="next_flight",
        value_fn=lambda flight, _now: flight["flight_number"] if flight else None,
        attributes_fn=_next_flight_attributes,
    ),
    NextFlightSensorDescription(
        key="next_flight_departure",
        translation_key="next_flight_departure",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda flight, _now: departure_time(flight) if flight else None,
    ),
    NextFlightSensorDescription(
        key="next_flight_arrival",
        translation_key="next_flight_arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda flight, _now: arrival_time(flight) if flight else None,
    ),
    NextFlightSensorDescription(
        key="next_flight_phase",
        translation_key="next_flight_phase",
        device_class=SensorDeviceClass.ENUM,
        options=PHASES,
        value_fn=flight_phase,
    ),
)

STATS_SENSORS: tuple[StatsSensorDescription, ...] = (
    StatsSensorDescription(
        key="total_flights",
        translation_key="total_flights",
        stat_key="flights",
        state_class=SensorStateClass.TOTAL,
    ),
    StatsSensorDescription(
        key="total_distance",
        translation_key="total_distance",
        stat_key="distance_km",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL,
    ),
    StatsSensorDescription(
        key="total_flight_time",
        translation_key="total_flight_time",
        stat_key="hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL,
    ),
    StatsSensorDescription(key="airports", translation_key="airports", stat_key="airports"),
    StatsSensorDescription(key="countries", translation_key="countries", stat_key="countries"),
    StatsSensorDescription(key="airlines", translation_key="airlines", stat_key="airlines"),
    StatsSensorDescription(
        key="upcoming_flights",
        translation_key="upcoming_flights",
        # null when the token's owner can't see planned flights -> unknown.
        stat_key="upcoming_flights",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TravelHistoryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        NextFlightSensor(coordinator, description) for description in NEXT_FLIGHT_SENSORS
    ]
    entities += [StatsSensor(coordinator, description) for description in STATS_SENSORS]
    async_add_entities(entities)


class NextFlightSensor(TravelHistoryEntity, SensorEntity):
    entity_description: NextFlightSensorDescription

    def __init__(
        self, coordinator: TravelHistoryCoordinator, description: NextFlightSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.next_flight(), dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.next_flight())


class StatsSensor(TravelHistoryEntity, SensorEntity):
    entity_description: StatsSensorDescription

    def __init__(
        self, coordinator: TravelHistoryCoordinator, description: StatsSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.coordinator.data.stats.get(self.entity_description.stat_key)
