"""Integration-specific entry and option helpers built on pyairbnk."""

from __future__ import annotations

# ruff: noqa: F401
import string
from collections.abc import Mapping, Sequence
from typing import Any

from homeassistant.const import CONF_NAME
from pyairbnk import (
    SUPPORTED_MODELS,
    AdvertisementData,
    AirbnkProtocolError,
    BatteryBreakpoint,
    BootstrapData,
    StatusResponseData,
    battery_profile_from_legacy_thresholds,
    battery_profile_from_voltage_points,
    battery_profile_to_storage,
    calculate_battery_percentage,
    decrypt_bootstrap,
    extract_manufacturer_payload,
    generate_operation_code,
    normalize_battery_profile,
    normalize_mac_address,
    parse_advertisement_data,
    parse_status_response,
    serial_numbers_match,
    split_operation_frames,
)
from pyairbnk.protocol import _AESCipher

from .const import (
    CONF_APP_KEY,
    CONF_BATTERY_PROFILE,
    CONF_BINDING_KEY,
    CONF_COMMAND_TIMEOUT,
    CONF_CONNECTIVITY_PROBE_INTERVAL,
    CONF_HARDWARE_VERSION,
    CONF_LOCK_ICON,
    CONF_LOCK_MODEL,
    CONF_LOCK_SN,
    CONF_MAC_ADDRESS,
    CONF_MANUFACTURER_KEY,
    CONF_NEW_SNINFO,
    CONF_PROFILE,
    CONF_RETRY_COUNT,
    CONF_REVERSE_COMMANDS,
    CONF_SUPPORTS_REMOTE_LOCK,
    CONF_UNAVAILABLE_AFTER,
    CONF_VOLTAGE_THRESHOLDS,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_CONNECTIVITY_PROBE_INTERVAL,
    DEFAULT_LOCK_ICON,
    DEFAULT_NAME,
    DEFAULT_RETRY_COUNT,
    DEFAULT_REVERSE_COMMANDS,
    DEFAULT_UNAVAILABLE_AFTER,
)
from .profiles import get_model_profile

_MDI_ICON_CHARACTERS = frozenset(string.ascii_lowercase + string.digits + "-")


def normalize_lock_icon(value: Any) -> str:
    """Normalize an optional MDI icon name stored in entry options."""

    icon = str(value or "").strip().lower()
    if not icon:
        return DEFAULT_LOCK_ICON
    if not icon.startswith("mdi:"):
        raise AirbnkProtocolError("lock_icon must be a valid mdi: icon")

    icon_name = icon.removeprefix("mdi:")
    if not icon_name or any(char not in _MDI_ICON_CHARACTERS for char in icon_name):
        raise AirbnkProtocolError("lock_icon must be a valid mdi: icon")

    return icon


def build_entry_data(
    *,
    mac_address: str,
    bootstrap: BootstrapData,
    battery_profile: Sequence[BatteryBreakpoint] | Sequence[Mapping[str, float]],
    hardware_version: str | None = None,
) -> dict[str, Any]:
    """Build stored connection data from bootstrap and user choices."""

    model_profile = get_model_profile(bootstrap.lock_model)
    normalized_battery_profile = normalize_battery_profile(battery_profile)

    return {
        CONF_LOCK_SN: bootstrap.lock_sn,
        CONF_LOCK_MODEL: bootstrap.lock_model,
        CONF_PROFILE: model_profile.key,
        CONF_MAC_ADDRESS: normalize_mac_address(mac_address),
        CONF_MANUFACTURER_KEY: bootstrap.manufacturer_key.hex(),
        CONF_BINDING_KEY: bootstrap.binding_key.hex(),
        CONF_BATTERY_PROFILE: battery_profile_to_storage(normalized_battery_profile),
        CONF_HARDWARE_VERSION: (hardware_version or "").strip(),
    }


def validate_entry_options(
    options: Mapping[str, Any],
    *,
    lock_model: str,
    legacy_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize and validate stored entry options."""

    model_profile = get_model_profile(lock_model)

    def _value(key: str, default: Any) -> Any:
        if key in options:
            return options[key]
        if legacy_data is not None and key in legacy_data:
            return legacy_data[key]
        return default

    supports_remote_lock_value: bool | None
    if CONF_SUPPORTS_REMOTE_LOCK in options:
        supports_remote_lock_value = options[CONF_SUPPORTS_REMOTE_LOCK]
    elif legacy_data is not None and CONF_SUPPORTS_REMOTE_LOCK in legacy_data:
        supports_remote_lock_value = legacy_data[CONF_SUPPORTS_REMOTE_LOCK]
    else:
        supports_remote_lock_value = model_profile.supports_remote_lock

    retry_count = int(_value(CONF_RETRY_COUNT, DEFAULT_RETRY_COUNT))
    command_timeout = int(_value(CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT))
    connectivity_probe_interval = int(
        _value(
            CONF_CONNECTIVITY_PROBE_INTERVAL,
            DEFAULT_CONNECTIVITY_PROBE_INTERVAL,
        )
    )
    unavailable_after = int(_value(CONF_UNAVAILABLE_AFTER, DEFAULT_UNAVAILABLE_AFTER))

    normalized: dict[str, Any] = {
        CONF_NAME: str(_value(CONF_NAME, DEFAULT_NAME)).strip() or DEFAULT_NAME,
        CONF_LOCK_ICON: normalize_lock_icon(_value(CONF_LOCK_ICON, DEFAULT_LOCK_ICON)),
        CONF_REVERSE_COMMANDS: bool(
            _value(CONF_REVERSE_COMMANDS, DEFAULT_REVERSE_COMMANDS)
        ),
        CONF_SUPPORTS_REMOTE_LOCK: bool(supports_remote_lock_value),
        CONF_RETRY_COUNT: retry_count,
        CONF_COMMAND_TIMEOUT: command_timeout,
        CONF_CONNECTIVITY_PROBE_INTERVAL: connectivity_probe_interval,
        CONF_UNAVAILABLE_AFTER: unavailable_after,
    }

    if retry_count < 0:
        raise AirbnkProtocolError("retry_count must be 0 or greater")
    if command_timeout < 1:
        raise AirbnkProtocolError("command_timeout must be at least 1 second")
    if connectivity_probe_interval < 0:
        raise AirbnkProtocolError("connectivity_probe_interval must be 0 or greater")
    if unavailable_after < 1:
        raise AirbnkProtocolError("unavailable_after must be at least 1 second")

    return normalized


def build_entry_options(
    *,
    name: str | None,
    lock_model: str,
    lock_icon: str | None = DEFAULT_LOCK_ICON,
    reverse_commands: bool = DEFAULT_REVERSE_COMMANDS,
    supports_remote_lock: bool | None = None,
    retry_count: int = DEFAULT_RETRY_COUNT,
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
    connectivity_probe_interval: int = DEFAULT_CONNECTIVITY_PROBE_INTERVAL,
    unavailable_after: int = DEFAULT_UNAVAILABLE_AFTER,
) -> dict[str, Any]:
    """Build stored entry options from user-tunable settings."""

    raw_options: dict[str, Any] = {
        CONF_NAME: (name or DEFAULT_NAME).strip() or DEFAULT_NAME,
        CONF_LOCK_ICON: normalize_lock_icon(lock_icon),
        CONF_REVERSE_COMMANDS: bool(reverse_commands),
        CONF_RETRY_COUNT: int(retry_count),
        CONF_COMMAND_TIMEOUT: int(command_timeout),
        CONF_CONNECTIVITY_PROBE_INTERVAL: int(connectivity_probe_interval),
        CONF_UNAVAILABLE_AFTER: int(unavailable_after),
    }
    if supports_remote_lock is not None:
        raw_options[CONF_SUPPORTS_REMOTE_LOCK] = bool(supports_remote_lock)
    return validate_entry_options(raw_options, lock_model=lock_model)


def migrate_legacy_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert an older local-entry format into normalized data and options."""

    bootstrap = decrypt_bootstrap(
        str(data[CONF_LOCK_SN]).strip(),
        str(data[CONF_NEW_SNINFO]).strip(),
        str(data[CONF_APP_KEY]).strip(),
    )
    battery_profile = battery_profile_from_legacy_thresholds(
        data[CONF_VOLTAGE_THRESHOLDS]
    )

    migrated_data = build_entry_data(
        mac_address=str(data[CONF_MAC_ADDRESS]),
        bootstrap=bootstrap,
        battery_profile=battery_profile,
        hardware_version=str(data.get(CONF_HARDWARE_VERSION, "")).strip(),
    )
    migrated_options = validate_entry_options(
        options,
        lock_model=bootstrap.lock_model,
        legacy_data=data,
    )
    return migrated_data, migrated_options


def migrate_legacy_entry_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Convert an older local-entry format into the public connection data."""

    migrated_data, _migrated_options = migrate_legacy_entry(data, {})
    return migrated_data


def validate_entry(
    data: Mapping[str, Any],
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], BootstrapData]:
    """Normalize and validate stored config-entry data and options."""

    if (
        (
            CONF_LOCK_MODEL not in data
            or CONF_MANUFACTURER_KEY not in data
            or CONF_BINDING_KEY not in data
            or CONF_BATTERY_PROFILE not in data
        )
        and CONF_NEW_SNINFO in data
        and CONF_APP_KEY in data
        and CONF_VOLTAGE_THRESHOLDS in data
    ):
        data, options = migrate_legacy_entry(data, options)

    lock_sn = str(data[CONF_LOCK_SN]).strip()
    if not lock_sn:
        raise AirbnkProtocolError("lock_sn is required")

    lock_model = str(data[CONF_LOCK_MODEL]).strip()
    if not lock_model:
        raise AirbnkProtocolError("lock_model is required")

    try:
        model_profile = get_model_profile(lock_model)
    except KeyError as err:
        supported = ", ".join(sorted(SUPPORTED_MODELS))
        raise AirbnkProtocolError(
            f"Unsupported Airbnk lock model '{lock_model}'. "
            f"Supported models: {supported}"
        ) from err

    normalized_data: dict[str, Any] = {
        CONF_MAC_ADDRESS: normalize_mac_address(str(data[CONF_MAC_ADDRESS])),
        CONF_LOCK_SN: lock_sn,
        CONF_LOCK_MODEL: lock_model,
        CONF_PROFILE: str(data.get(CONF_PROFILE) or model_profile.key),
        CONF_MANUFACTURER_KEY: _normalize_key_hex(
            data[CONF_MANUFACTURER_KEY], "manufacturer_key"
        ),
        CONF_BINDING_KEY: _normalize_key_hex(data[CONF_BINDING_KEY], "binding_key"),
        CONF_BATTERY_PROFILE: battery_profile_to_storage(
            normalize_battery_profile(data[CONF_BATTERY_PROFILE])
        ),
        CONF_HARDWARE_VERSION: str(data.get(CONF_HARDWARE_VERSION, "")).strip(),
    }

    if normalized_data[CONF_PROFILE] != model_profile.key:
        raise AirbnkProtocolError(
            f"profile '{normalized_data[CONF_PROFILE]}' does not match "
            f"lock model '{lock_model}'"
        )

    normalized_options = validate_entry_options(
        options,
        lock_model=lock_model,
        legacy_data=data,
    )

    bootstrap = BootstrapData(
        lock_sn=lock_sn,
        lock_model=lock_model,
        profile=model_profile.key,
        manufacturer_key=bytes.fromhex(normalized_data[CONF_MANUFACTURER_KEY]),
        binding_key=bytes.fromhex(normalized_data[CONF_BINDING_KEY]),
    )
    return normalized_data, normalized_options, bootstrap


def validate_entry_data(
    data: Mapping[str, Any],
) -> tuple[dict[str, Any], BootstrapData]:
    """Compatibility wrapper for callers that only care about entry data."""

    normalized_data, _normalized_options, bootstrap = validate_entry(data, {})
    return normalized_data, bootstrap


def _normalize_key_hex(value: Any, label: str) -> str:
    """Normalize a stored hex key."""

    text = str(value).strip().lower()
    if len(text) < 32 or len(text) % 2:
        raise AirbnkProtocolError(f"{label} must be an even-length hex string")
    try:
        bytes.fromhex(text)
    except ValueError as err:
        raise AirbnkProtocolError(f"{label} is not valid hex") from err
    return text
