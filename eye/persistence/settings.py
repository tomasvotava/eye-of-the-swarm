from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from eye.persistence.codec import SaveDataError

if TYPE_CHECKING:
    from typing_extensions import TypeIs

SETTINGS_SCHEMA_VERSION = 1


class WindowScale(StrEnum):
    """How big the game window is. `AUTO` is whatever size SDL picks for the scaled window at boot;
    the value strings are the persisted form."""

    AUTO = "auto"
    X1 = "x1"
    X2 = "x2"
    X3 = "x3"
    X4 = "x4"
    FULLSCREEN = "fullscreen"


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    schema_version: int
    combat_speed_multiplier: float
    window_scale: WindowScale = WindowScale.AUTO


def default_settings() -> SettingsSnapshot:
    return SettingsSnapshot(schema_version=SETTINGS_SCHEMA_VERSION, combat_speed_multiplier=1.0)


def encode_settings(settings: SettingsSnapshot) -> str:
    payload = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "combat_speed_multiplier": settings.combat_speed_multiplier,
        "window_scale": settings.window_scale.value,
    }
    return json.dumps(payload)


def decode_settings(data: str) -> SettingsSnapshot:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SaveDataError(f"settings data is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SaveDataError(f"settings data must be a JSON object, got {type(payload).__name__}")

    schema_version = payload.get("schema_version")
    if schema_version != SETTINGS_SCHEMA_VERSION:
        raise SaveDataError(f"unsupported schema_version: {schema_version!r}")

    combat_speed_multiplier = payload.get("combat_speed_multiplier")
    if not _is_number(combat_speed_multiplier) or combat_speed_multiplier <= 0:
        raise SaveDataError(f"combat_speed_multiplier must be a positive number, got {combat_speed_multiplier!r}")

    # Absent from blobs written before the setting existed -- additive, so no schema bump.
    raw_window_scale = payload.get("window_scale", WindowScale.AUTO.value)
    try:
        window_scale = WindowScale(raw_window_scale)
    except ValueError as exc:
        raise SaveDataError(f"unknown window_scale: {raw_window_scale!r}") from exc

    return SettingsSnapshot(
        schema_version=SETTINGS_SCHEMA_VERSION,
        combat_speed_multiplier=float(combat_speed_multiplier),
        window_scale=window_scale,
    )


def _is_number(value: Any) -> TypeIs[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
