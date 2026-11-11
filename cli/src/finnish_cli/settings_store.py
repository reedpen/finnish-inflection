"""Versioned, portable persistence for drill selections."""

import json
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_config_dir

from finnish_core.settings import VALID_SELECTION_IDS, DrillSettings

APP_NAME = "finnish-inflection-cli"
SETTINGS_VERSION = 1


class SettingsStore:
    def __init__(self, path: str | Path | None = None):
        self.path = (
            Path(path) if path else Path(user_config_dir(APP_NAME)) / "settings.json"
        )

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                isinstance(data, dict)
                and data.get("version") == SETTINGS_VERSION
                and isinstance(data.get("last"), dict)
            ):
                return data
        except (OSError, ValueError, TypeError):
            pass
        return {"version": SETTINGS_VERSION, "last": {}}

    def load(self, drill: str) -> DrillSettings | None:
        raw = self._read()["last"].get(drill)
        if not isinstance(raw, dict) or raw.get("drill") != drill:
            return None
        selections = raw.get("selections")
        length = raw.get("session_length")
        if not isinstance(selections, dict) or not all(
            isinstance(values, list) and all(isinstance(value, str) for value in values)
            for values in selections.values()
        ):
            return None
        schema = VALID_SELECTION_IDS.get(drill)
        if (
            schema is None
            or set(selections) != set(schema)
            or any(
                not values or not set(values).issubset(schema[key])
                for key, values in selections.items()
            )
        ):
            return None
        if length is not None and (
            not isinstance(length, int) or isinstance(length, bool) or length < 1
        ):
            return None
        return DrillSettings(drill, selections, length)

    def has_saved(self, drill: str) -> bool:
        return drill in self._read()["last"]

    def save(self, settings: DrillSettings) -> None:
        data = self._read()
        data["last"][settings.drill] = asdict(settings)
        data["recent_drill"] = settings.drill
        self._write(data)

    def load_recent(self) -> DrillSettings | None:
        recent = self._read().get("recent_drill")
        return self.load(recent) if isinstance(recent, str) else None

    def reset(self, drill: str | None = None) -> None:
        data = self._read()
        if drill is None:
            data = {"version": SETTINGS_VERSION, "last": {}}
        else:
            data["last"].pop(drill, None)
            if data.get("recent_drill") == drill:
                data.pop("recent_drill", None)
        self._write(data)

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)
