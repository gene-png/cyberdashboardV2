import json
import os
from flask import current_app

_cache: dict = {}


def load_framework(framework_id: str) -> dict:
    if framework_id in _cache:
        return _cache[framework_id]
    path = os.path.join(current_app.config["FRAMEWORKS_DIR"], f"{framework_id}.json")
    with open(path, "r") as f:
        data = json.load(f)
    _cache[framework_id] = data
    return data


def get_activity(framework_id: str, activity_id: str) -> dict | None:
    fw = load_framework(framework_id)
    for pillar in fw["pillars"]:
        for activity in pillar["activities"]:
            if activity["id"] == activity_id:
                return activity
    return None


def get_pillar(framework_id: str, pillar_id: str) -> dict | None:
    fw = load_framework(framework_id)
    for pillar in fw["pillars"]:
        if pillar["id"] == pillar_id:
            return pillar
    return None


def list_frameworks() -> list[str]:
    frameworks_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "frameworks")
    frameworks_dir = os.path.abspath(frameworks_dir)
    return [f.replace(".json", "") for f in os.listdir(frameworks_dir) if f.endswith(".json")]
