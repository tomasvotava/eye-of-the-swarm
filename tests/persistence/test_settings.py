import pytest

from eye.persistence.codec import SaveDataError
from eye.persistence.settings import SETTINGS_SCHEMA_VERSION, SettingsSnapshot, decode_settings, encode_settings


def test_encode_then_decode_round_trips_the_settings() -> None:
    settings = SettingsSnapshot(schema_version=1, combat_speed_multiplier=2.0)

    decoded = decode_settings(encode_settings(settings))

    assert decoded == settings


def test_encode_always_stamps_the_current_schema_version_even_if_the_snapshot_disagrees() -> None:
    stale = SettingsSnapshot(schema_version=999, combat_speed_multiplier=2.0)

    decoded = decode_settings(encode_settings(stale))

    assert decoded.schema_version == SETTINGS_SCHEMA_VERSION


def test_decode_rejects_invalid_json() -> None:
    with pytest.raises(SaveDataError):
        decode_settings("not json")


def test_decode_rejects_a_non_object_payload() -> None:
    with pytest.raises(SaveDataError):
        decode_settings("[1, 2, 3]")


def test_decode_rejects_an_unsupported_schema_version() -> None:
    with pytest.raises(SaveDataError):
        decode_settings('{"schema_version": 999, "combat_speed_multiplier": 1.0}')


def test_decode_rejects_a_missing_combat_speed_multiplier() -> None:
    with pytest.raises(SaveDataError):
        decode_settings('{"schema_version": 1}')


def test_decode_rejects_a_non_numeric_combat_speed_multiplier() -> None:
    with pytest.raises(SaveDataError):
        decode_settings('{"schema_version": 1, "combat_speed_multiplier": "fast"}')


def test_decode_accepts_an_integral_combat_speed_multiplier() -> None:
    decoded = decode_settings('{"schema_version": 1, "combat_speed_multiplier": 2}')

    assert decoded.combat_speed_multiplier == 2.0


def test_decode_rejects_a_zero_combat_speed_multiplier() -> None:
    # Threaded straight into a Phase's duration_seconds division (ADR 0017) -- zero would raise
    # ZeroDivisionError mid-combat rather than at load time.
    with pytest.raises(SaveDataError):
        decode_settings('{"schema_version": 1, "combat_speed_multiplier": 0}')


def test_decode_rejects_a_negative_combat_speed_multiplier() -> None:
    with pytest.raises(SaveDataError):
        decode_settings('{"schema_version": 1, "combat_speed_multiplier": -1.5}')
