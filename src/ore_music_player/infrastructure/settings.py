from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

_MIGRATION_KEY = "_meta/legacy_registry_migrated"
_LEGACY_ORGANIZATION = "OreMusicPlayer"
_LEGACY_APPLICATION = "OreMusicPlayer"


def load_settings(settings_path: str | Path) -> QSettings:
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = QSettings(str(path), QSettings.Format.IniFormat)

    if not path.exists():
        _migrate_legacy_settings(settings)

    return settings


def _migrate_legacy_settings(settings: QSettings) -> None:
    legacy_settings = QSettings(
        _LEGACY_ORGANIZATION,
        _LEGACY_APPLICATION,
    )
    legacy_keys = legacy_settings.allKeys()
    if legacy_keys:
        for key in legacy_keys:
            if not settings.contains(key):
                settings.setValue(key, legacy_settings.value(key))

    settings.setValue(_MIGRATION_KEY, True)
    settings.sync()
