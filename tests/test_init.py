"""Integration lifecycle tests for Airbnk BLE."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airbnk_ble import (
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.airbnk_ble.const import DOMAIN

from .common import build_bootstrap_fixture


async def test_async_setup_initializes_domain_storage(hass: HomeAssistant) -> None:
    """Top-level setup should initialize hass.data for the domain."""

    assert await async_setup(hass, {}) is True
    assert DOMAIN in hass.data


async def test_async_setup_entry_normalizes_legacy_entry_data(
    hass: HomeAssistant,
) -> None:
    """Entry setup should normalize older entry data before runtime startup."""

    fixture = build_bootstrap_fixture()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front Gate",
        data={
            "name": "Front Gate",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "lock_sn": fixture["lock_sn"],
            "new_sninfo": fixture["new_sninfo"],
            "app_key": fixture["app_key"],
            "voltage_thresholds": [2.5, 2.6, 2.9],
            "reverse_commands": False,
            "supports_remote_lock": False,
            "retry_count": 3,
            "command_timeout": 15,
            "connectivity_probe_interval": 0,
            "unavailable_after": 60,
        },
    )
    runtime = MagicMock()
    runtime.async_start = AsyncMock()
    runtime.async_stop = MagicMock()

    with (
        patch(
            "custom_components.airbnk_ble.AirbnkLockRuntime",
            return_value=runtime,
        ) as runtime_cls,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(return_value=None),
        ),
        patch.object(hass.config_entries, "async_update_entry") as update_entry,
    ):
        assert await async_setup_entry(hass, entry) is True

    runtime.async_start.assert_awaited_once()
    runtime_cls.assert_called_once()
    update_entry.assert_called_once()
    assert update_entry.call_args.kwargs["options"]["name"] == "Front Gate"
    assert entry.runtime_data is runtime


async def test_async_setup_entry_removes_retired_debug_entities(
    hass: HomeAssistant,
) -> None:
    """Entry setup should prune stale raw-debug entities from the registry."""

    fixture = build_bootstrap_fixture()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front Gate",
        data={
            "lock_sn": fixture["lock_sn"],
            "lock_model": fixture["lock_model"],
            "profile": "b100",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "manufacturer_key": fixture["manufacturer_key"].hex(),
            "binding_key": fixture["binding_key"].hex(),
            "battery_profile": [
                {"voltage": 2.3, "percent": 0.0},
                {"voltage": 2.9, "percent": 100.0},
            ],
            "hardware_version": "",
        },
        options={
            "name": "Front Gate",
            "lock_icon": "",
            "reverse_commands": False,
            "supports_remote_lock": False,
            "retry_count": 3,
            "command_timeout": 15,
            "connectivity_probe_interval": 0,
            "unavailable_after": 60,
        },
    )
    registry = MagicMock()
    runtime = MagicMock()
    runtime.async_start = AsyncMock()
    runtime.async_stop = MagicMock()

    with (
        patch(
            "custom_components.airbnk_ble.AirbnkLockRuntime",
            return_value=runtime,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(return_value=None),
        ),
        patch("custom_components.airbnk_ble.er.async_get", return_value=registry),
        patch(
            "custom_components.airbnk_ble.er.async_entries_for_config_entry",
            return_value=[
                SimpleNamespace(
                    unique_id=f"{fixture['lock_sn']}_advert_state_bits",
                    entity_id="sensor.front_gate_advert_state_bits",
                ),
                SimpleNamespace(
                    unique_id=f"{fixture['lock_sn']}_battery",
                    entity_id="sensor.front_gate_battery",
                ),
            ],
        ),
    ):
        assert await async_setup_entry(hass, entry) is True

    registry.async_remove.assert_called_once_with(
        "sensor.front_gate_advert_state_bits"
    )


async def test_async_unload_entry_delegates_to_config_entries(
    hass: HomeAssistant,
) -> None:
    """Unload helper should delegate to the HA config manager."""

    entry = MockConfigEntry(domain=DOMAIN, title="Front Gate", data={})

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ) as unload_platforms:
        assert await async_unload_entry(hass, entry) is True

    unload_platforms.assert_awaited_once()


async def test_async_remove_entry_triggers_bluetooth_rediscovery(
    hass: HomeAssistant,
) -> None:
    """Removing an entry should allow Bluetooth discovery to fire again."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front Gate",
        data={"mac_address": "AA:BB:CC:DD:EE:FF"},
    )

    with patch(
        "custom_components.airbnk_ble.bluetooth.async_rediscover_address"
    ) as async_rediscover_address:
        await async_remove_entry(hass, entry)

    async_rediscover_address.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF")
