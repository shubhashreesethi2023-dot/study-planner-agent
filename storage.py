"""Persistent state for the Study Planner Agent (a single JSON file)."""
import copy
import json
import os
import tempfile
from pathlib import Path

DEFAULT_PATH = Path(os.environ.get("PLANNER_DATA", "data/state.json"))

EMPTY_STATE = {
    "next_id": 1,
    "tasks": [],
    "settings": {"daily_hours": 4.0, "max_block_hours": 2.0},
    "blocked_dates": {},  # "YYYY-MM-DD" -> reason
    "schedule": [],       # last generated schedule (list of day dicts)
}


class Store:
    """Tiny JSON-file store. load() -> dict, save(dict) writes atomically."""

    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_PATH

    def load(self):
        if not self.path.exists():
            return copy.deepcopy(EMPTY_STATE)
        with open(self.path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # fill any keys missing from older files
        for key, value in EMPTY_STATE.items():
            state.setdefault(key, copy.deepcopy(value))
        return state

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
