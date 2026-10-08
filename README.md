# Travel History for Home Assistant

Custom integration that brings flights from a [Travel History](https://fly.urvfr.one) server into Home Assistant: the next flight, a flights calendar, an "in flight" sensor and lifetime stats.

Access is **read-only**: the integration uses a server API token that can't change anything.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/zloi-litovets/ha-travel-history`, category **Integration**.
2. Install **Travel History**, restart Home Assistant.

### Manual

Copy `custom_components/travel_history` into your HA `config/custom_components/` and restart.

## Setup

1. On the Travel History site, open the admin → **Integrations** and create a token. It's shown once, so copy it.
2. In HA: **Settings → Devices & services → Add integration → Travel History**, then enter the site URL and the token.

The token sees what its owner sees: planned (future) flights only while the owner is a staff user. If the token is revoked or expires, HA asks to re-authenticate. The URL or token can be changed later with **Reconfigure**.

## Entities

| Entity | Description |
|---|---|
| `sensor.*_next_flight` | Flight number of the flight in the air now or the next planned one. A flight that landed under 30 minutes ago stays here (phase `landed`) unless the following one has already departed. Attributes: route, airline, aircraft, seat, airports (IATA code - null if the airport has none, name, city, country), local times |
| `sensor.*_next_flight_departure` / `_arrival` | Scheduled times (`timestamp`) - usable directly in time triggers |
| `sensor.*_next_flight_phase` | `upcoming`, `in_air`, `landed` or `none` |
| `binary_sensor.*_in_flight` | On while the next flight is between its scheduled departure and arrival |
| `calendar.*_flights` | All flights (past and planned) as calendar events |
| `sensor.*_total_flights`, `_total_distance`, `_total_flight_time`, `_airports`, `_countries`, `_airlines` | Stats over flights that have happened |
| `sensor.*_upcoming_flights` | Number of planned flights (unknown if the token can't see them) |

Data is polled every 5 minutes. Phases are computed from scheduled times, so they can lag by up to one poll. There's no live flight status yet.

### Example automation

```yaml
triggers:
  - trigger: calendar
    event: start
    offset: "-3:00:00"
    entity_id: calendar.fly_example_com_flights
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.calendar_event.summary }} departs in 3 hours"
```

## Development

```sh
pip install -r requirements_test.txt
pytest
```
