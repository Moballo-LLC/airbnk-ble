"""Cloud API tests for Airbnk BLE."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.airbnk_ble.cloud_api import (
    AIRBNK_VERSION,
    AirbnkCloudClient,
    AirbnkCloudError,
    AirbnkCloudSession,
)


class _MockResponse:
    """Minimal async response wrapper for cloud API tests."""

    def __init__(self, payload, *, status: int = 200):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, *, content_type=None):
        return self._payload


async def test_request_verification_code_preserves_plus_addressing() -> None:
    """Verification-code requests should preserve '+' email aliases."""

    session = SimpleNamespace(
        request=MagicMock(return_value=_MockResponse({"code": 200}))
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    await client.async_request_verification_code("user+locks@example.com")

    request_kwargs = session.request.call_args.kwargs
    assert request_kwargs["params"]["loginAcct"] == "user+locks@example.com"
    assert request_kwargs["params"]["version"] == AIRBNK_VERSION
    assert request_kwargs["timeout"] is not None


async def test_authenticate_preserves_plus_addressing() -> None:
    """Token requests should preserve '+' email aliases."""

    session = SimpleNamespace(
        request=MagicMock(
            return_value=_MockResponse(
                {
                    "code": 200,
                    "data": {
                        "email": "user+locks@example.com",
                        "userId": "user-id",
                        "token": "token",
                    },
                }
            )
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    result = await client.async_authenticate("user+locks@example.com", "123456")

    assert result.email == "user+locks@example.com"
    request_kwargs = session.request.call_args.kwargs
    assert request_kwargs["params"]["loginAcct"] == "user+locks@example.com"


async def test_get_locks_filters_incomplete_and_non_lock_devices() -> None:
    """Cloud lock fetch should keep only complete supported lock records."""

    session = SimpleNamespace(
        request=MagicMock(
            return_value=_MockResponse(
                {
                    "code": 200,
                    "data": [
                        {
                            "sn": "LOCK-1",
                            "deviceName": "Front Gate",
                            "deviceType": "B100",
                            "hardwareVersion": "1",
                            "appKey": "app-key-1",
                            "newSninfo": "bootstrap-1",
                        },
                        {
                            "sn": "WIFI-1",
                            "deviceName": "Gateway",
                            "deviceType": "W100",
                            "hardwareVersion": "1",
                            "appKey": "app-key-2",
                            "newSninfo": "bootstrap-2",
                        },
                        {
                            "sn": "BROKEN-1",
                            "deviceName": "Broken",
                            "deviceType": "B100",
                        },
                    ],
                }
            )
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    locks = await client.async_get_locks(
        AirbnkCloudSession(
            email="user@example.com",
            user_id="user-id",
            token="token",
        )
    )

    assert [lock.serial_number for lock in locks] == ["LOCK-1"]
    assert locks[0].device_name == "Front Gate"


async def test_get_battery_profile_maps_voltage_curve() -> None:
    """Cloud voltage config should become a stored breakpoint profile."""

    session = SimpleNamespace(
        request=MagicMock(
            return_value=_MockResponse(
                {
                    "code": 200,
                    "data": {
                        "voltageCfg": [
                            {
                                "fdeviceType": "B100",
                                "fhardwareVersion": "1",
                                "fvoltage1": 2.4,
                                "fvoltage2": 2.6,
                                "fvoltage3": 2.8,
                                "fvoltage4": 3.0,
                            }
                        ]
                    },
                }
            )
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    profile = await client.async_get_battery_profile(
        AirbnkCloudSession(
            email="user@example.com",
            user_id="user-id",
            token="token",
        ),
        lock_model="B100",
        hardware_version="1",
    )

    assert profile == [
        {"voltage": 2.4, "percent": 0.0},
        {"voltage": 2.6, "percent": 33.3},
        {"voltage": 2.8, "percent": 66.7},
        {"voltage": 3.0, "percent": 100.0},
    ]


async def test_async_call_raises_for_http_errors() -> None:
    """Non-200 responses should fail the cloud flow."""

    session = SimpleNamespace(
        request=MagicMock(return_value=_MockResponse({"code": 500}, status=500))
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    with pytest.raises(AirbnkCloudError, match="HTTP 500"):
        await client._async_call("GET", "/test", {})  # noqa: SLF001


async def test_async_call_raises_for_missing_data() -> None:
    """Responses without data should fail when data is expected."""

    session = SimpleNamespace(
        request=MagicMock(return_value=_MockResponse({"code": 200}))
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    with pytest.raises(AirbnkCloudError, match="did not include any data"):
        await client._async_call("GET", "/test", {})  # noqa: SLF001


async def test_async_call_raises_with_info_field_message() -> None:
    """Cloud errors should surface the server's 'info' field."""

    session = SimpleNamespace(
        request=MagicMock(
            return_value=_MockResponse(
                {"code": 500, "info": "Update app:https://we-here.com/en/app.html "}
            )
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    with pytest.raises(AirbnkCloudError, match="Update app:"):
        await client._async_call("POST", "/test", {}, expect_data=False)  # noqa: SLF001


async def test_async_request_retries_after_timeout() -> None:
    """Transient transport failures should be retried once."""

    session = SimpleNamespace(
        request=MagicMock(side_effect=[TimeoutError(), _MockResponse({"code": 200})])
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock()  # noqa: SLF001

    result = await client._async_request("POST", "/test", {})  # noqa: SLF001

    assert result == {"code": 200}
    assert session.request.call_count == 2
    client._async_get_ipv4_session.assert_not_awaited()


async def test_async_request_falls_back_to_ipv4_after_shared_timeout() -> None:
    """Timeouts on the shared HA session should fall back to an IPv4 session."""

    shared_session = SimpleNamespace(request=MagicMock(side_effect=TimeoutError()))
    ipv4_session = SimpleNamespace(
        request=MagicMock(return_value=_MockResponse({"code": 200}))
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = shared_session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock(return_value=ipv4_session)  # noqa: SLF001

    result = await client._async_request("POST", "/test", {})  # noqa: SLF001

    assert result == {"code": 200}
    assert shared_session.request.call_count == 2
    client._async_get_ipv4_session.assert_awaited_once()
    assert ipv4_session.request.call_count == 1


async def test_async_request_raises_helpful_transport_error() -> None:
    """Repeated transport failures should raise a cloud error."""

    shared_session = SimpleNamespace(request=MagicMock(side_effect=TimeoutError()))
    ipv4_session = SimpleNamespace(
        request=MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=None,
                os_error=OSError("network down"),
            )
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = shared_session  # noqa: SLF001
    client._ipv4_session = None  # noqa: SLF001
    client._async_get_ipv4_session = AsyncMock(return_value=ipv4_session)  # noqa: SLF001

    with pytest.raises(AirbnkCloudError) as err:
        await client._async_request(
            "POST",
            "/api/lock/sms",
            {"loginAcct": "user@example.com"},
        )  # noqa: SLF001

    assert str(err.value) == "Could not reach the Airbnk cloud: Connection error"
    assert "user@example.com" not in str(err.value)
