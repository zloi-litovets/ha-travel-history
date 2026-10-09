# Travel History for Home Assistant

Custom integration that brings flights from a [Travel History](https://fly.urvfr.one) server into Home Assistant: the next flight with its live status (gate, delays, baggage belt), a flights calendar, an "in flight" sensor and lifetime stats.

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
| `sensor.*_next_flight_phase` | `upcoming`, `in_air`, `landed`, `cancelled` or `none` |
| `binary_sensor.*_in_flight` | On while the next flight is in the air (live times when tracked, otherwise scheduled) |
| `calendar.*_flights` | All flights (past and planned) as calendar events |
| `sensor.*_total_flights`, `_total_distance`, `_total_flight_time`, `_airports`, `_countries`, `_airlines` | Stats over flights that have happened |
| `sensor.*_upcoming_flights` | Number of planned flights (unknown if the token can't see them) |

### Live flight status

When the server has live tracking enabled (Travel History admin → **Tracking**), the next flight also gets these. They stay `unknown` until the server's provider has found the flight, usually from 24 hours before departure.

| Entity | Description |
|---|---|
| `sensor.*_next_flight_status` | `scheduled`, `delayed`, `departed` (left the gate), `en_route`, `landed`, `arrived`, `cancelled`, `diverted` |
| `sensor.*_next_flight_expected_departure` / `_expected_arrival` | Actual time if known, else the latest estimate (`timestamp`). Attributes: scheduled, actual, delay, terminal, gate (and baggage belt for arrival) |
| `sensor.*_next_flight_departure_delay` | Departure delay in minutes (negative = early) |
| `sensor.*_next_flight_gate` | Departure gate, terminal as an attribute |
| `sensor.*_next_flight_baggage_belt` | Baggage belt on arrival, terminal as an attribute |

`sensor.*_next_flight` also gets `live_status`, `departure_gate`, `departure_terminal`, `arrival_gate`, `arrival_terminal`, `baggage_belt`, `live_registration`, `schedule_changed` and `diverted_to` attributes (all null while the flight isn't tracked).

`*_next_flight_departure` / `_arrival` keep showing the recorded (scheduled) times. Phase and **In flight** follow live times when the flight is tracked, so a delayed flight stays `upcoming` / `in_air` for as long as the delay lasts.

Every change live tracking reports is also fired as a `travel_history_flight_change` event. Data: `kind` (`schedule_change`, `delay`, `gate`, `terminal`, `baggage`, `registration`, `status`, `cancelled`, `diverted`), `field`, `old`, `new`, `flight_id`, `flight_number`, `at`, `entry_id`. Only changes after Home Assistant started are fired.

Data is polled every 5 minutes; the server itself checks the provider every 15 minutes to 2 hours depending on how close the flight is. Works with servers without live tracking too, where these sensors just stay `unknown`.

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

Notify about a gate change:

```yaml
triggers:
  - trigger: event
    event_type: travel_history_flight_change
    event_data:
      kind: gate
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.event.data.flight_number }}: gate {{ trigger.event.data.new }}"
```

## Development

```sh
pip install -r requirements_test.txt
pytest
```
