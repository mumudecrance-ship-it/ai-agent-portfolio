#!/usr/bin/env python3
import json
from pathlib import Path
import sys


def validate(data):
    errors = []
    if data.get("task_type") != "large_event_egress_simulation":
        errors.append("task_type")
    for key in ("event", "exits", "groups", "candidates"):
        if not data.get(key):
            errors.append(key)
    if data.get("event") and data.get("groups"):
        total = sum(int(item.get("people", 0)) for item in data["groups"])
        if total != int(data["event"].get("audience_count", -1)):
            errors.append("groups.people_total")
    exit_ids = {item.get("id") for item in data.get("exits", [])}
    for candidate in data.get("candidates", []):
        for gid, prefs in candidate.get("preferences", {}).items():
            if not prefs or not set(prefs).issubset(exit_ids):
                errors.append(f"candidate.{candidate.get('id')}.{gid}.preferences")
    return sorted(set(errors))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_case.py <case.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    errors = validate(payload)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)
