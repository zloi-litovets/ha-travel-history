"""Config flow tests."""

from __future__ import annotations

from http import HTTPStatus

import aiohttp

from homeassistant import config_entries
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.travel_history.const import DOMAIN

from .conftest import API, TOKEN, URL

USER_INPUT = {CONF_URL: f"{URL}/", CONF_API_TOKEN: f" {TOKEN} ", CONF_VERIFY_SSL: True}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_user_flow_success(hass: HomeAssistant, mock_api) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "fly.example.com"
    # Trailing slash and token whitespace are normalized away.
    assert result["data"] == {CONF_URL: URL, CONF_API_TOKEN: TOKEN, CONF_VERIFY_SSL: True}
    assert result["result"].unique_id == URL
    assert mock_api.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_user_flow_invalid_auth_then_recover(hass: HomeAssistant, aioclient_mock, mock_api) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}whoami/", status=HTTPStatus.UNAUTHORIZED)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}whoami/", json={"token": {}, "can_see_future_flights": True})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{API}whoami/", exc=aiohttp.ClientConnectionError())
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_server_error(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{API}whoami/", status=HTTPStatus.INTERNAL_SERVER_ERROR)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_url(hass: HomeAssistant, aioclient_mock) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_URL: "fly.example.com"}
    )
    assert result["errors"] == {CONF_URL: "invalid_url"}
    assert aioclient_mock.call_count == 0


async def test_user_flow_already_configured(hass: HomeAssistant, config_entry, mock_api) -> None:
    config_entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, config_entry, aioclient_mock, mock_api) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}whoami/", status=HTTPStatus.UNAUTHORIZED)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_TOKEN: "trv_bad"})
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}whoami/", json={"token": {}, "can_see_future_flights": True})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_TOKEN: "trv_new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_API_TOKEN] == "trv_new"


async def test_reconfigure_moves_to_new_url(hass: HomeAssistant, config_entry, mock_api, aioclient_mock) -> None:
    config_entry.add_to_hass(hass)
    new_url = "https://flights.example.org"
    aioclient_mock.get(f"{new_url}/api/ext/v1/whoami/", json={"token": {}, "can_see_future_flights": True})

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: new_url, CONF_API_TOKEN: "trv_other", CONF_VERIFY_SSL: False}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.unique_id == new_url
    assert config_entry.title == "flights.example.org"
    assert config_entry.data == {CONF_URL: new_url, CONF_API_TOKEN: "trv_other", CONF_VERIFY_SSL: False}
