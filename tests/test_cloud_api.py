"""Cloud API tests for Airbnk BLE."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

from custom_components.airbnk_ble.cloud_api import (
    AIRBNK_VERSION,
    AirbnkCloudClient,
    AirbnkCloudError,
    AirbnkCloudSession,
)


class _MockResponse:
    """Minimal sync response wrapper for cloud API tests."""

    def __init__(self, payload, *, status_code: int = 200):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


async def test_request_verification_code_preserves_plus_addressing() -> None:
    """Verification-code requests should preserve '+' email aliases."""

    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(return_value=_MockResponse({"code": 200}))
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._hass = hass  # noqa: SLF001

    await client.async_request_verification_code("user+locks@example.com")

    assert hass.async_add_executor_job.await_count == 1
    request_callable = hass.async_add_executor_job.await_args.args[0]
    assert request_callable.args[0] == "POST"
    assert "loginAcct=user%2Blocks%40example.com" in request_callable.args[1]
    assert f"version={AIRBNK_VERSION}" in request_callable.args[1]


async def test_authenticate_preserves_plus_addressing() -> None:
    """Token requests should preserve '+' email aliases."""

    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(
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
    client._hass = hass  # noqa: SLF001

    result = await client.async_authenticate("user+locks@example.com", "123456")

    assert result.email == "user+locks@example.com"
    request_callable = hass.async_add_executor_job.await_args.args[0]
    assert request_callable.args[0] == "GET"
    assert "loginAcct=user%2Blocks%40example.com" in request_callable.args[1]


async def test_get_locks_filters_incomplete_and_non_lock_devices() -> None:
    """Cloud lock fetch should keep only complete supported lock records."""

    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(
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
    client._hass = hass  # noqa: SLF001

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

    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(
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
    client._hass = hass  # noqa: SLF001

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

    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._async_request = AsyncMock(  # noqa: SLF001
        return_value=_MockResponse({"code": 500}, status_code=500)
    )

    with pytest.raises(AirbnkCloudError, match="HTTP 500"):
        await client._async_call("GET", "/test", {})  # noqa: SLF001


async def test_async_call_raises_for_missing_data() -> None:
    """Responses without data should fail when data is expected."""

    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._async_request = AsyncMock(return_value=_MockResponse({"code": 200}))  # noqa: SLF001

    with pytest.raises(AirbnkCloudError, match="did not include any data"):
        await client._async_call("GET", "/test", {})  # noqa: SLF001


async def test_async_call_raises_with_info_field_message() -> None:
    """Cloud errors should surface the server's 'info' field."""

    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._async_request = AsyncMock(  # noqa: SLF001
        return_value=_MockResponse(
            {"code": 500, "info": "Update app:https://we-here.com/en/app.html "}
        )
    )

    with pytest.raises(AirbnkCloudError, match="Update app:"):
        await client._async_call("POST", "/test", {}, expect_data=False)  # noqa: SLF001


async def test_async_request_retries_after_timeout() -> None:
    """Transient transport failures should be retried once."""

    response = _MockResponse({"code": 200})
    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(
            side_effect=[requests.Timeout("slow"), response]
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._hass = hass  # noqa: SLF001

    result = await client._async_request("POST", "https://example.com/test")  # noqa: SLF001

    assert result is response
    assert hass.async_add_executor_job.await_count == 2


async def test_async_request_raises_helpful_transport_error() -> None:
    """Repeated transport failures should raise a cloud error."""

    hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(
            side_effect=requests.Timeout(
                "Connection timeout to host "
                "https://wehereapi.seamooncloud.com/api/lock/sms"
                "?loginAcct=user%40example.com"
            )
        )
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._hass = hass  # noqa: SLF001

    with pytest.raises(AirbnkCloudError) as err:
        await client._async_request("POST", "https://example.com/test")  # noqa: SLF001

    assert str(err.value) == "Could not reach the Airbnk cloud: Connection timeout"
    assert "user@example.com" not in str(err.value)
