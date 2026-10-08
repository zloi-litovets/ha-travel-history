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
LANDED_GRACE = timedelta(minutes=30)

PHASE_UPCOMING = "upcoming"
PHASE_IN_AIR = "in_air"
PHASE_LANDED = "landed"
PHASE_NONE = "none"
PHASES = [PHASE_UPCOMING, PHASE_IN_AIR, PHASE_LANDED, PHASE_NONE]
