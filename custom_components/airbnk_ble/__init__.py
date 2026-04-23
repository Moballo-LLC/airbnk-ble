"""Airbnk BLE integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .airbnk import validate_entry
from .const import CONF_LOCK_SN, CONF_MAC_ADDRESS, DOMAIN, PLATFORMS
from .device import AirbnkLockRuntime

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_OBSOLETE_ENTITY_KEYS: frozenset[str] = frozenset(
    {
        "state_source",
        "last_advert_age",
        "lock_events_counter",
        "advert_state_byte",
        "advert_state_bits",
        "advert_state_meaning",
        "status_state_byte",
        "status_state_bits",
        "status_state_meaning",
        "status_tail_byte",
        "last_error",
    }
)


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the Airbnk BLE integration."""

    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Airbnk BLE from a config entry."""

    normalized_data, normalized_options, bootstrap = validate_entry(
        entry.data,
        entry.options,
    )
    if normalized_data != dict(entry.data) or normalized_options != dict(entry.options):
        hass.config_entries.async_update_entry(
            entry,
            data=normalized_data,
            options=normalized_options,
            title=normalized_options["name"],
        )
    _async_remove_obsolete_entities(hass, entry, str(normalized_data[CONF_LOCK_SN]))

    runtime = AirbnkLockRuntime(hass, entry, bootstrap)
    entry.runtime_data = runtime
    await runtime.async_start()
    entry.async_on_unload(runtime.async_stop)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Trigger Bluetooth rediscovery when an entry is removed."""

    bluetooth.async_rediscover_address(hass, str(entry.data[CONF_MAC_ADDRESS]))


def _async_remove_obsolete_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    lock_sn: str,
) -> None:
    """Remove retired debug entities from the entity registry."""

    registry = er.async_get(hass)
    obsolete_unique_ids = {f"{lock_sn}_{key}" for key in _OBSOLETE_ENTITY_KEYS}
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id in obsolete_unique_ids:
            registry.async_remove(registry_entry.entity_id)
