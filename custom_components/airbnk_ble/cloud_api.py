"""Airbnk cloud helpers for bootstrap acquisition."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.const import CONF_EMAIL
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)

from .airbnk import AirbnkProtocolError, battery_profile_from_voltage_points

_LOGGER = logging.getLogger(__name__)

AIRBNK_CLOUD_URL = "https://wehereapi.seamooncloud.com"
AIRBNK_LANGUAGE = "2"
AIRBNK_VERSION = "A_FD_2.1.8"
AIRBNK_HEADERS = {
    "user-agent": "okhttp/3.12.0",
    "Accept-Encoding": "gzip, deflate",
}
AIRBNK_RETRY_ATTEMPTS = 2
AIRBNK_TIMEOUT = ClientTimeout(total=45, connect=20, sock_connect=20, sock_read=30)


class AirbnkCloudError(RuntimeError):
    """Raised when the Airbnk cloud flow cannot proceed."""


@dataclass(frozen=True, slots=True)
class AirbnkCloudSession:
    """Authenticated cloud session details."""

    email: str
    user_id: str
    token: str


@dataclass(frozen=True, slots=True)
class AirbnkCloudLock:
    """Lock details returned from the Airbnk cloud."""

    serial_number: str
    device_name: str
    lock_model: str
    hardware_version: str
    app_key: str
    new_sninfo: str


class AirbnkCloudClient:
    """Fetch bootstrap data from the Airbnk cloud."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._session = async_get_clientsession(hass)
        self._ipv4_session: ClientSession | None = None

    async def async_request_verification_code(self, email: str) -> None:
        """Request an email verification code."""

        await self._async_call(
            "POST",
            "/api/lock/sms",
            {
                "loginAcct": email,
                "language": AIRBNK_LANGUAGE,
                "version": AIRBNK_VERSION,
                "mark": "10",
                "userId": "",
            },
            expect_data=False,
        )

    async def async_authenticate(self, email: str, code: str) -> AirbnkCloudSession:
        """Authenticate and return a short-lived session."""

        payload = await self._async_call(
            "GET",
            "/api/lock/loginByAuthcode",
            {
                "loginAcct": email,
                "authCode": code,
                "systemCode": "Android",
                "language": AIRBNK_LANGUAGE,
                "version": AIRBNK_VERSION,
                "deviceID": "123456789012345",
                "mark": "1",
            },
        )

        try:
            data = payload["data"]
            return AirbnkCloudSession(
                email=str(data[CONF_EMAIL]),
                user_id=str(data["userId"]),
                token=str(data["token"]),
            )
        except (KeyError, TypeError) as err:
            raise AirbnkCloudError(
                "The Airbnk login response was missing required fields"
            ) from err

    async def async_get_locks(
        self, session: AirbnkCloudSession
    ) -> list[AirbnkCloudLock]:
        """Return supported locks for the authenticated account."""

        payload = await self._async_call(
            "GET",
            "/api/v2/lock/getAllDevicesNew",
            {
                "language": AIRBNK_LANGUAGE,
                "userId": session.user_id,
                "version": AIRBNK_VERSION,
                "token": session.token,
            },
        )

        locks: list[AirbnkCloudLock] = []
        for raw_lock in payload.get("data") or []:
            try:
                lock = AirbnkCloudLock(
                    serial_number=str(raw_lock["sn"]),
                    device_name=str(raw_lock.get("deviceName") or raw_lock["sn"]),
                    lock_model=str(raw_lock["deviceType"]),
                    hardware_version=str(raw_lock.get("hardwareVersion") or ""),
                    app_key=str(raw_lock["appKey"]),
                    new_sninfo=str(raw_lock["newSninfo"]),
                )
            except (KeyError, TypeError) as err:
                _LOGGER.debug("Skipping incomplete Airbnk cloud record: %s", raw_lock)
                _LOGGER.debug("Incomplete Airbnk cloud record error: %s", err)
                continue
            if lock.lock_model.startswith(("W", "F")):
                continue
            locks.append(lock)

        return locks

    async def async_get_battery_profile(
        self,
        session: AirbnkCloudSession,
        *,
        lock_model: str,
        hardware_version: str,
    ) -> list[dict[str, float]] | None:
        """Fetch the cloud voltage config and convert it into a battery profile."""

        payload = await self._async_call(
            "GET",
            "/api/lock/getAllInfo1",
            {
                "language": AIRBNK_LANGUAGE,
                "userId": session.user_id,
                "version": AIRBNK_VERSION,
                "token": session.token,
            },
        )

        voltage_configs = (payload.get("data") or {}).get("voltageCfg") or []
        for raw_profile in voltage_configs:
            if (
                str(raw_profile.get("fdeviceType")) != lock_model
                or str(raw_profile.get("fhardwareVersion")) != hardware_version
            ):
                continue
            try:
                profile = battery_profile_from_voltage_points(
                    [
                        float(raw_profile[f"fvoltage{index}"])
                        for index in range(1, 5)
                        if raw_profile.get(f"fvoltage{index}") is not None
                    ]
                )
            except (AirbnkProtocolError, ValueError, TypeError):
                return None
            return [
                {"voltage": point.voltage, "percent": point.percent}
                for point in profile
            ]

        return None

    async def _async_call(
        self,
        method: str,
        path: str,
        params: dict[str, str],
        *,
        expect_data: bool = True,
    ) -> dict[str, Any]:
        """Call an Airbnk cloud endpoint and validate the response."""

        payload = await self._async_request(method, path, params)

        if payload.get("code") != 200:
            raise AirbnkCloudError(
                str(
                    payload.get("info")
                    or payload.get("msg")
                    or payload.get("message")
                    or "Airbnk cloud rejected the request"
                )
            )
        if expect_data and "data" not in payload:
            raise AirbnkCloudError("Airbnk cloud response did not include any data")
        return payload

    async def _async_request(
        self,
        method: str,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """Perform an Airbnk HTTP request with HA-managed client sessions."""

        last_err: Exception | None = None
        endpoint = f"{AIRBNK_CLOUD_URL}{path}"

        sessions: list[tuple[str, ClientSession]] = [("shared", self._session)]
        for session_label, session in sessions:
            for attempt in range(1, AIRBNK_RETRY_ATTEMPTS + 1):
                try:
                    async with session.request(
                        method,
                        endpoint,
                        headers=AIRBNK_HEADERS,
                        params=params,
                        timeout=AIRBNK_TIMEOUT,
                    ) as response:
                        if response.status != 200:
                            raise AirbnkCloudError(
                                "Airbnk cloud request failed with HTTP "
                                f"{response.status}"
                            )
                        try:
                            return await response.json(content_type=None)
                        except ValueError as err:
                            raise AirbnkCloudError(
                                "Airbnk cloud returned invalid JSON"
                            ) from err
                except (TimeoutError, ClientError) as err:
                    last_err = err
                    if attempt == AIRBNK_RETRY_ATTEMPTS:
                        break
                    _LOGGER.debug(
                        "Retrying Airbnk cloud request via %s session after %s "
                        "(%s/%s): %s",
                        session_label,
                        type(err).__name__,
                        attempt,
                        AIRBNK_RETRY_ATTEMPTS,
                        endpoint,
                    )

        if isinstance(last_err, TimeoutError):
            ipv4_session = await self._async_get_ipv4_session()
            for attempt in range(1, AIRBNK_RETRY_ATTEMPTS + 1):
                try:
                    async with ipv4_session.request(
                        method,
                        endpoint,
                        headers=AIRBNK_HEADERS,
                        params=params,
                        timeout=AIRBNK_TIMEOUT,
                    ) as response:
                        if response.status != 200:
                            raise AirbnkCloudError(
                                "Airbnk cloud request failed with HTTP "
                                f"{response.status}"
                            )
                        try:
                            return await response.json(content_type=None)
                        except ValueError as err:
                            raise AirbnkCloudError(
                                "Airbnk cloud returned invalid JSON"
                            ) from err
                except (TimeoutError, ClientError) as err:
                    last_err = err
                    if attempt == AIRBNK_RETRY_ATTEMPTS:
                        break
                    _LOGGER.debug(
                        "Retrying Airbnk cloud request via IPv4 session after %s "
                        "(%s/%s): %s",
                        type(err).__name__,
                        attempt,
                        AIRBNK_RETRY_ATTEMPTS,
                        endpoint,
                    )

        raise AirbnkCloudError(
            f"Could not reach the Airbnk cloud: {_describe_transport_error(last_err)}"
        ) from last_err

    async def _async_get_ipv4_session(self) -> ClientSession:
        """Return an HA-managed IPv4-only client session."""

        if self._ipv4_session is None or self._ipv4_session.closed:
            self._ipv4_session = async_create_clientsession(
                self._hass,
                family=socket.AF_INET,
            )
        return self._ipv4_session


def _describe_transport_error(err: Exception | None) -> str:
    """Return a log-safe description for a transport failure."""

    if err is None:
        return "Request failed"
    if isinstance(err, TimeoutError):
        return "Connection timeout"
    if isinstance(err, ClientError):
        return "Connection error"
    return type(err).__name__
