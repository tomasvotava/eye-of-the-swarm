import json
from dataclasses import dataclass
from typing import Any, TypeIs

from eye.persistence.codec import SaveDataError

SETTINGS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    schema_version: int
    combat_speed_multiplier: float


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
    if not _is_number(combat_speed_multiplier):
        raise SaveDataError(f"combat_speed_multiplier must be a number, got {combat_speed_multiplier!r}")

    return SettingsSnapshot(
        schema_version=SETTINGS_SCHEMA_VERSION,
        combat_speed_multiplier=float(combat_speed_multiplier),
    )


def _is_number(value: Any) -> TypeIs[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
