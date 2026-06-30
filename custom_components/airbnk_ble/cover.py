"""Optional cover platform for Airbnk BLE locks."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import AirbnkBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the optional Airbnk cover entity."""

    runtime = entry.runtime_data
    if runtime.expose_cover:
        async_add_entities([AirbnkBleCover(runtime)])


class AirbnkBleCover(AirbnkBaseEntity, CoverEntity):
    """Cover-style entity for users who prefer open/close lock controls."""

    _attr_name = "Cover"
    _attr_device_class = CoverDeviceClass.DOOR
    _attr_has_entity_name = True

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._attr_unique_id = f"{runtime.lock_sn}_cover"

    @property
    def available(self) -> bool:
        """Return true when the lock has been seen recently enough."""

        return (
            self._runtime.state.lock_state is not None
            or (not self._runtime.has_advertisement)
            or self._runtime.state.available
        )

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return cover operations supported by this lock configuration."""

        features = CoverEntityFeature(0)
        if self._runtime.supports_remote_unlock:
            features |= CoverEntityFeature.OPEN
        if self._runtime.supports_remote_lock:
            features |= CoverEntityFeature.CLOSE
        return features

    @property
    def is_closed(self) -> bool | None:
        """Return whether the cover-style lock is closed."""

        return self._runtime.is_locked

    @property
    def is_closing(self) -> bool:
        """Return whether a close/lock command is in progress."""

        return self._runtime.is_locking

    @property
    def is_opening(self) -> bool:
        """Return whether an open/unlock command is in progress."""

        return self._runtime.is_unlocking

    @property
    def current_cover_position(self) -> int | None:
        """Map lock state to a simple closed/open cover position."""

        if self._runtime.is_locked is True:
            return 0
        if self._runtime.is_locked is False:
            return 100
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return capability hints for the optional cover entity."""

        return {
            "remote_lock_supported": self._runtime.supports_remote_lock,
            "remote_unlock_supported": self._runtime.supports_remote_unlock,
        }

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open/unlock the Airbnk device."""

        await self._runtime.async_open()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close/lock the Airbnk device."""

        await self._runtime.async_lock()
