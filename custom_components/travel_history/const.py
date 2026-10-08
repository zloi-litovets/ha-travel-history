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

PHASE_UPCOMING = "upcoming"
PHASE_IN_AIR = "in_air"
PHASE_LANDED = "landed"
PHASE_NONE = "none"
PHASES = [PHASE_UPCOMING, PHASE_IN_AIR, PHASE_LANDED, PHASE_NONE]
