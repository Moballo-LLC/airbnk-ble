"""Home Assistant wrapper around the standalone pyairbnk cloud client."""

from __future__ import annotations

import socket

from aiohttp import ClientSession
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from pyairbnk import (
    AIRBNK_VERSION,
    AirbnkCloudError,
    AirbnkCloudLock,
    AirbnkCloudSession,
)
from pyairbnk import (
    AirbnkCloudClient as _BaseAirbnkCloudClient,
)


class AirbnkCloudClient(_BaseAirbnkCloudClient):
    """Fetch bootstrap data from the Airbnk cloud using HA-managed sessions."""

    def __init__(self, hass) -> None:
        shared_session = async_get_clientsession(hass)
        ipv4_session = async_create_clientsession(hass, family=socket.AF_INET)
        super().__init__(
            shared_session,
            ipv4_session=ipv4_session,
            app_version=AIRBNK_VERSION,
        )


__all__ = [
    "AIRBNK_VERSION",
    "AirbnkCloudClient",
    "AirbnkCloudError",
    "AirbnkCloudLock",
    "AirbnkCloudSession",
    "ClientSession",
]
