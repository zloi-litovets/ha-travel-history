"""Binary sensors for Travel History."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import PHASE_IN_AIR
from .coordinator import TravelHistoryConfigEntry, TravelHistoryCoordinator, flight_phase
from .entity import TravelHistoryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TravelHistoryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([InFlightBinarySensor(entry.runtime_data)])


class InFlightBinarySensor(TravelHistoryEntity, BinarySensorEntity):
    _attr_translation_key = "in_flight"

    def __init__(self, coordinator: TravelHistoryCoordinator) -> None:
        super().__init__(coordinator, "in_flight")

    @property
    def is_on(self) -> bool:
        now = dt_util.utcnow()
        return flight_phase(self.coordinator.data.next_flight(now), now) == PHASE_IN_AIR
