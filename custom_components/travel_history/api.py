"""Client for the Travel History read-only integrations API."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import aiohttp

from .const import API_PREFIX, REQUEST_TIMEOUT


class TravelHistoryError(Exception):
    """Base error talking to the Travel History server."""


class TravelHistoryAuthError(TravelHistoryError):
    """The API token is invalid, expired or revoked."""


class TravelHistoryConnectionError(TravelHistoryError):
    """The server could not be reached or answered with an error."""


class TravelHistoryNotFoundError(TravelHistoryError):
    """Something answered at this address, but not the Travel History API
    (404, or a non-JSON page - e.g. the site URL was given with a path like
    /app, so the request hit the single-page app instead of the API).
    """


class TravelHistoryClient:
    """Thin async wrapper over /api/ext/v1/."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str) -> None:
        self._session = session
        self._api_url = base_url.rstrip("/") + API_PREFIX
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.get(self._api_url + path, headers=self._headers, params=params) as resp,
            ):
                if resp.status == 401:
                    raise TravelHistoryAuthError("Invalid, expired or revoked API token")
                if resp.status == 404:
                    raise TravelHistoryNotFoundError(f"404 from {resp.url}")
                resp.raise_for_status()
                try:
                    return await resp.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise TravelHistoryNotFoundError(
                        f"{resp.url} did not answer with JSON ({resp.content_type})"
                    ) from err
        except TravelHistoryError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise TravelHistoryConnectionError(str(err) or type(err).__name__) from err

    async def whoami(self) -> dict[str, Any]:
        return await self._get("whoami/")

    async def upcoming_flights(self, limit: int) -> list[dict[str, Any]]:
        payload = await self._get("flights/upcoming/", {"limit": str(limit)})
        return payload["flights"]

    async def flights(self, departed_from: datetime, departed_to: datetime) -> list[dict[str, Any]]:
        payload = await self._get(
            "flights/",
            {
                "from": departed_from.isoformat(),
                "to": departed_to.isoformat(),
                "order": "asc",
                "limit": "1000",
            },
        )
        return payload["flights"]

    async def stats(self) -> dict[str, Any]:
        return await self._get("stats/summary/")
