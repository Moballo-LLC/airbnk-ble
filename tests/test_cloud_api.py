"""Cloud API tests for Airbnk BLE."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.airbnk_ble.cloud_api import AirbnkCloudClient


class _MockResponse:
    """Minimal async response wrapper for cloud API tests."""

    def __init__(self, payload):
        self.status = 200
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, *, content_type=None):
        return self._payload


async def test_request_verification_code_preserves_plus_addressing() -> None:
    """Verification-code requests should preserve '+' email aliases."""

    session = AsyncMock()
    session.request.return_value = _MockResponse({"code": 200})
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001

    await client.async_request_verification_code("user+locks@example.com")

    assert session.request.await_count == 1
    request_kwargs = session.request.await_args.kwargs
    assert request_kwargs["params"]["loginAcct"] == "user+locks@example.com"


async def test_authenticate_preserves_plus_addressing() -> None:
    """Token requests should preserve '+' email aliases."""

    session = AsyncMock()
    session.request.return_value = _MockResponse(
        {
            "code": 200,
            "data": {
                "email": "user+locks@example.com",
                "userId": "user-id",
                "token": "token",
            },
        }
    )
    client = AirbnkCloudClient.__new__(AirbnkCloudClient)
    client._session = session  # noqa: SLF001

    result = await client.async_authenticate("user+locks@example.com", "123456")

    assert result.email == "user+locks@example.com"
    request_kwargs = session.request.await_args.kwargs
    assert request_kwargs["params"]["loginAcct"] == "user+locks@example.com"
