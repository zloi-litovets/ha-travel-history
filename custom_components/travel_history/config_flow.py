"""Config flow for Travel History."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    TravelHistoryAuthError,
    TravelHistoryClient,
    TravelHistoryError,
    TravelHistoryNotFoundError,
)
from .const import DOMAIN, LOGGER

_TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_API_TOKEN): _TOKEN_SELECTOR,
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
    }
)
STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_TOKEN): _TOKEN_SELECTOR})


def _normalize_url(url: str) -> str | None:
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return url


class TravelHistoryConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, url: str, token: str, verify_ssl: bool) -> dict[str, str]:
        """Returns form errors - empty when the token works."""
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        try:
            await TravelHistoryClient(session, url, token).whoami()
        except TravelHistoryAuthError:
            return {"base": "invalid_auth"}
        except TravelHistoryNotFoundError as err:
            LOGGER.warning("No Travel History API at %s: %s", url, err)
            return {"base": "not_travel_history"}
        except TravelHistoryError as err:
            LOGGER.warning("Could not connect to Travel History at %s: %s", url, err)
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unexpected error validating Travel History server")
            return {"base": "unknown"}
        return {}

    async def _validate_user_input(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        url = _normalize_url(user_input[CONF_URL])
        if url is None:
            return None, {CONF_URL: "invalid_url"}
        data = {**user_input, CONF_URL: url, CONF_API_TOKEN: user_input[CONF_API_TOKEN].strip()}
        errors = await self._validate(url, data[CONF_API_TOKEN], data[CONF_VERIFY_SSL])
        return (None if errors else data), errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input[CONF_URL])
            if url is not None:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
            data, errors = await self._validate_user_input(user_input)
            if data is not None:
                return self.async_create_entry(title=urlparse(data[CONF_URL]).hostname, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            errors = await self._validate(entry.data[CONF_URL], token, entry.data[CONF_VERIFY_SSL])
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_TOKEN: token})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate_user_input(user_input)
            if data is not None:
                if data[CONF_URL] != entry.unique_id:
                    # Moving to another server address - must not collide
                    # with a server that's already configured.
                    await self.async_set_unique_id(data[CONF_URL])
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=data[CONF_URL],
                    title=urlparse(data[CONF_URL]).hostname,
                    data_updates=data,
                )

        suggested = user_input or {
            CONF_URL: entry.data[CONF_URL],
            CONF_VERIFY_SSL: entry.data[CONF_VERIFY_SSL],
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, suggested),
            errors=errors,
        )
