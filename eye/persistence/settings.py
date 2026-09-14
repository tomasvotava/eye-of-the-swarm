from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from eye.persistence.codec import SaveDataError

if TYPE_CHECKING:
    from typing_extensions import TypeIs

SETTINGS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    schema_version: int
    combat_speed_multiplier: float


def default_settings() -> SettingsSnapshot:
    return SettingsSnapshot(schema_version=SETTINGS_SCHEMA_VERSION, combat_speed_multiplier=1.0)


def encode_settings(settings: SettingsSnapshot) -> str:
    payload = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "combat_speed_multiplier": settings.combat_speed_multiplier,
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

    return SettingsSnapshot(
        schema_version=SETTINGS_SCHEMA_VERSION,
        combat_speed_multiplier=float(combat_speed_multiplier),
    )


def _is_number(value: Any) -> TypeIs[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
