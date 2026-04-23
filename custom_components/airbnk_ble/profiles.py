"""Compatibility re-exports for supported Airbnk model profiles."""

from __future__ import annotations

from pyairbnk import (
    MODEL_PROFILE_BY_KEY,
    MODEL_PROFILE_BY_MODEL,
    MODEL_PROFILES,
    SUPPORTED_MODELS,
    BatteryBreakpoint,
    ModelProfile,
    get_model_profile,
)

__all__ = [
    "BatteryBreakpoint",
    "MODEL_PROFILE_BY_KEY",
    "MODEL_PROFILE_BY_MODEL",
    "MODEL_PROFILES",
    "ModelProfile",
    "SUPPORTED_MODELS",
    "get_model_profile",
]
