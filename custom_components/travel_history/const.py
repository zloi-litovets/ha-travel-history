"""Constants for the Travel History integration."""

from datetime import timedelta
import logging

DOMAIN = "travel_history"
LOGGER = logging.getLogger(__package__)

API_PREFIX = "/api/ext/v1/"
REQUEST_TIMEOUT = 30

# Flight data is schedule-based and changes only when the log is edited, so
# there's no point polling faster. Phases (upcoming / in the air / landed)
# are computed locally from the scheduled times on every update.
SCAN_INTERVAL = timedelta(minutes=5)
UPCOMING_LIMIT = 10

# How long a just-landed flight stays the "next flight" (phase `landed`)
# before the sensors move on - unless the following flight has already
# departed by then. Must stay under the server's own grace: flights/upcoming/
# keeps a landed flight for only 1 hour (FUTURE_FLIGHT_GRACE in
# travel_history/models.py), after which it's gone from the data entirely.
# A live-tracked flight is kept by the server until it actually lands.
LANDED_GRACE = timedelta(minutes=30)

PHASE_UPCOMING = "upcoming"
PHASE_IN_AIR = "in_air"
PHASE_LANDED = "landed"
PHASE_CANCELLED = "cancelled"
PHASE_NONE = "none"
PHASES = [PHASE_UPCOMING, PHASE_IN_AIR, PHASE_LANDED, PHASE_CANCELLED, PHASE_NONE]

# Live tracking (the flight's `live` block, servers with tracking enabled).
# The server's own "unknown" status is reported as the HA unknown state.
LIVE_STATUSES = [
    "scheduled",
    "delayed",
    "departed",
    "en_route",
    "landed",
    "arrived",
    "cancelled",
    "diverted",
]
# Fired on the HA bus for every change live tracking reports (gate, delay,
# cancellation...) - see tracking/events/ in the server's API docs.
EVENT_FLIGHT_CHANGE = f"{DOMAIN}_flight_change"
EVENTS_PAGE_SIZE = 100
EVENTS_MAX_PAGES = 5
