"""Deterministic multi-agent egress simulator for the fixed course case.

The course Skill defines the task contract and thresholds. This engine owns
repeatable calculations, fan-out/fan-in execution, candidate state, permission
boundaries and evidence digests. It never controls a real venue or map product.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parent
CASE_PATH = ROOT / "fixtures" / "main_event.json"
PROFILE_PATH = ROOT / "fixtures" / "project-profile.json"
COURSE_ROOT = ROOT
SKILL_ROOT = ROOT / "skill" / "simulate-event-egress-plan"
POLICY_PATH = SKILL_ROOT / "references" / "egress-policy.json"
SKILL_PATH = SKILL_ROOT / "SKILL.md"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_case() -> dict[str, Any]:
    return _read_json(CASE_PATH)


def load_profile() -> dict[str, Any]:
    return _read_json(PROFILE_PATH)


def load_policy() -> dict[str, Any]:
    return _read_json(POLICY_PATH)


def skill_evidence() -> dict[str, Any]:
    text = SKILL_PATH.read_text(encoding="utf-8")
    return {
        "name": "simulate-event-egress-plan",
        "path": str(SKILL_PATH.relative_to(COURSE_ROOT)),
        "sha256": sha256(text.encode("utf-8")).hexdigest(),
        "policy_version": load_policy()["policy_version"],
        "loaded": True,
    }


DIRECTION_POSITIONS = {
    "north": (50, 12),
    "northeast": (78, 22),
    "east": (88, 50),
    "southeast": (78, 78),
    "south": (50, 88),
    "southwest": (22, 78),
    "west": (12, 50),
    "northwest": (22, 22),
}


def _canonical_direction(value: Any, index: int) -> str:
    raw = str(value or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "北": "north", "north": "north", "n": "north",
        "东北": "northeast", "northeast": "northeast", "ne": "northeast",
        "东": "east", "east": "east", "e": "east",
        "东南": "southeast", "southeast": "southeast", "se": "southeast",
        "南": "south", "south": "south", "s": "south",
        "西南": "southwest", "southwest": "southwest", "sw": "southwest",
        "西": "west", "west": "west", "w": "west",
        "西北": "northwest", "northwest": "northwest", "nw": "northwest",
    }
    return aliases.get(raw, list(DIRECTION_POSITIONS)[index % len(DIRECTION_POSITIONS)])


def build_case_from_venue(venue_config: dict[str, Any]) -> dict[str, Any]:
    """Create a bounded deterministic case from one editable personal venue profile.

    The profile is code-validated before it can reach the simulator. Free-form
    event wording is handled by the model, but people, exits and capacities are
    never guessed by the model or read from a production map.
    """

    if not isinstance(venue_config, dict):
        raise ValueError("场馆档案必须是一个对象")
    name = str(venue_config.get("name") or "").strip()
    if not name or len(name) > 60:
        raise ValueError("场馆名称必须在 1—60 个字符之间")
    try:
        audience_count = int(venue_config.get("audience_count"))
    except (TypeError, ValueError) as exc:
        raise ValueError("总人数必须是整数") from exc
    if not 100 <= audience_count <= 200_000:
        raise ValueError("总人数需在 100—200,000 之间")

    submitted_exits = venue_config.get("exits")
    if not isinstance(submitted_exits, list) or not 2 <= len(submitted_exits) <= 8:
        raise ValueError("请配置 2—8 个出口")
    exits: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_exit in enumerate(submitted_exits):
        if not isinstance(raw_exit, dict):
            raise ValueError("每个出口都必须包含名称、容量和方位")
        exit_id = str(raw_exit.get("id") or f"E{index + 1}").strip().upper()
        exit_name = str(raw_exit.get("name") or "").strip()
        if not exit_id or len(exit_id) > 12 or exit_id in seen_ids:
            raise ValueError("出口 ID 不能为空、超过 12 个字符或重复")
        if not exit_name or len(exit_name) > 40:
            raise ValueError(f"{exit_id} 的出口名称必须在 1—40 个字符之间")
        try:
            capacity = int(raw_exit.get("capacity_per_tick"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{exit_id} 的每轮容量必须是整数") from exc
        if not 20 <= capacity <= 20_000:
            raise ValueError(f"{exit_id} 的每轮容量需在 20—20,000 之间")
        direction = _canonical_direction(raw_exit.get("direction"), index)
        x, y = DIRECTION_POSITIONS[direction]
        exits.append({
            "id": exit_id,
            "name": exit_name,
            "direction": direction,
            "capacity_per_tick": capacity,
            "safe_queue": max(capacity * 3, 100),
            "x": x,
            "y": y,
        })
        seen_ids.add(exit_id)

    raw_groups = venue_config.get("groups")
    groups: list[dict[str, Any]] = []
    if isinstance(raw_groups, list) and raw_groups:
        if len(raw_groups) > 8:
            raise ValueError("客群或分区最多配置 8 组")
        for index, raw_group in enumerate(raw_groups):
            if not isinstance(raw_group, dict):
                raise ValueError("客群配置格式无效")
            people = int(raw_group.get("people") or 0)
            if people <= 0:
                raise ValueError("每个客群的人数必须大于 0")
            preferred = [str(item).strip().upper() for item in raw_group.get("preferred_exit_ids", [])]
            preferred = [item for item in preferred if item in seen_ids]
            groups.append({
                "id": str(raw_group.get("id") or f"G{index + 1}").strip().upper(),
                "name": str(raw_group.get("name") or f"客群 {index + 1}").strip(),
                "people": people,
                "release_per_tick": max(1, (people + 5) // 6),
                "origin": f"S{index + 1}",
                "x": 35 + (index % 3) * 15,
                "y": 38 + (index // 3) * 15,
                "preferred_exit_ids": preferred,
            })
        if sum(item["people"] for item in groups) != audience_count:
            raise ValueError("客群人数合计必须等于总人数")
    else:
        group_count = min(4, len(exits))
        base, remainder = divmod(audience_count, group_count)
        for index in range(group_count):
            people = base + (1 if index < remainder else 0)
            groups.append({
                "id": f"G{index + 1}",
                "name": f"分区客群 {index + 1}",
                "people": people,
                "release_per_tick": max(1, (people + 5) // 6),
                "origin": f"S{index + 1}",
                "x": 36 + (index % 2) * 28,
                "y": 38 + (index // 2) * 24,
                "preferred_exit_ids": [exits[index % len(exits)]["id"]],
            })

    exit_ids = [item["id"] for item in exits]
    capacity_rank = [item["id"] for item in sorted(exits, key=lambda item: (-item["capacity_per_tick"], item["id"]))]
    nearest: dict[str, list[str]] = {}
    balanced: dict[str, list[str]] = {}
    transit_first: dict[str, list[str]] = {}
    for index, group in enumerate(groups):
        supplied = [item for item in group.pop("preferred_exit_ids", []) if item in seen_ids]
        first = supplied[0] if supplied else exit_ids[index % len(exit_ids)]
        nearest[group["id"]] = [first, *[item for item in exit_ids if item != first]]
        offset = index % len(capacity_rank)
        rotated = capacity_rank[offset:] + capacity_rank[:offset]
        balanced[group["id"]] = rotated
        transit_first[group["id"]] = capacity_rank

    public_profile = {
        "name": name,
        "audience_count": audience_count,
        "zone_notes": str(venue_config.get("zone_notes") or "").strip()[:2000],
        "exits": exits,
    }
    case_id = f"personal-{stable_digest(public_profile)[:12]}"
    return {
        "case_id": case_id,
        "task_type": "large_event_egress_simulation",
        "task_name": f"{name}散场推演",
        "captured_at": "LOCAL_SESSION",
        "event": {
            "venue": name,
            "audience_count": audience_count,
            "show_end": "USER_DEFINED",
            "tick_minutes": 2,
            "max_ticks": 12,
        },
        "exits": exits,
        "groups": groups,
        "events": [],
        "candidates": [
            {"id": "A", "name": "就近优先", "description": "沿初始偏好分流，不做事件后的局部重规划。", "replan_mode": "none", "reroute_ratio": 0.0, "preferences": nearest},
            {"id": "B", "name": "容量感知均衡", "description": "保留备用出口余量，只重规划受影响客群。", "replan_mode": "capacity_aware", "reroute_ratio": 0.75, "preferences": balanced},
            {"id": "C", "name": "高运力优先", "description": "优先使用高容量出口，拥堵后再有限改道。", "replan_mode": "late", "reroute_ratio": 0.35, "preferences": transit_first},
        ],
        "personal_profile": public_profile,
    }


def apply_live_preview(case: dict[str, Any], preview: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge a confirmed live preview into a copy of the fixed case.

    This is intentionally a narrow adapter: the LLM can add or replace
    capacity events inside the Profile window, but it cannot alter people,
    candidates, thresholds, permissions or any real-world action.
    """

    if preview.get("mode") != "API_PREVIEW" or preview.get("adapter_status") != "OK" or preview.get("live_request") is not True:
        raise ValueError("实时输入还没有通过 API 适配器校验")
    if not preview.get("requires_human_confirmation"):
        raise ValueError("实时输入缺少人工确认标记")
    expires_at = preview.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("实时输入的有效期格式无效") from exc
        if expiry <= datetime.now(timezone.utc):
            raise ValueError("实时输入预览已过期，请重新请求")
    profile = load_profile()
    allowed_kinds = set(profile.get("allowed_change_kinds", []))
    window = profile.get("step_window", {})
    exits = {item["id"] for item in case.get("exits", [])}
    updated = deepcopy(case)
    existing = list(updated.get("events", []))
    added_ids: list[str] = []
    for change in preview.get("changes", []):
        target = change.get("target")
        kind = change.get("kind")
        start = change.get("start_step")
        end = change.get("end_step")
        if target not in exits or kind not in allowed_kinds:
            raise ValueError("实时输入超出项目 Profile 允许的对象或变化类型")
        if not isinstance(start, int) or not isinstance(end, int) or start < window.get("min", 0) or end > window.get("max", -1) or start > end:
            raise ValueError("实时输入超出项目 Profile 允许的轮次范围")
        if kind in {"EXIT_CLOSED", "TRANSIT_CLOSED"}:
            multiplier = 0.0
        else:
            raw_value = change.get("value")
            if isinstance(raw_value, dict):
                raw_value = raw_value.get("capacity_multiplier", raw_value.get("multiplier"))
            try:
                multiplier = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("实时输入的容量变化值必须是 0 到 1 之间的数字") from exc
            if not 0 <= multiplier <= 1:
                raise ValueError("实时输入的容量变化值必须是 0 到 1 之间的数字")
        event_id = f"LIVE-{stable_digest({key: change.get(key) for key in ('kind', 'target', 'start_step', 'end_step', 'value', 'description')})[:10]}"
        new_event = {
            "id": event_id,
            "name": change.get("description", "实时输入变化"),
            "exit_id": target,
            "start_tick": start,
            "end_tick": end,
            "capacity_multiplier": multiplier,
            "source": "API_PREVIEW",
            "preview_id": preview.get("preview_id"),
        }
        # A new live event replaces an overlapping event for the same exit;
        # this prevents accidental double multiplication of capacity.
        existing = [
            event for event in existing
            if not (
                event.get("exit_id") == target
                and int(event.get("start_tick", 0)) <= end
                and int(event.get("end_tick", 0)) >= start
            )
        ]
        existing.append(new_event)
        added_ids.append(event_id)
    updated["events"] = sorted(existing, key=lambda item: (int(item.get("start_tick", 0)), item.get("id", "")))
    return updated, [event["id"] for event in updated["events"]]


def stable_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def validate_case(case: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("event", "exits", "groups", "candidates"):
        if not case.get(key):
            missing.append(key)
    event = case.get("event", {})
    for key in ("audience_count", "tick_minutes", "max_ticks"):
        if not event.get(key):
            missing.append(f"event.{key}")
    people = sum(int(item.get("people", 0)) for item in case.get("groups", []))
    if event.get("audience_count") and people != int(event["audience_count"]):
        missing.append("groups.people_total")
    exit_ids = [item.get("id") for item in case.get("exits", [])]
    group_ids = [item.get("id") for item in case.get("groups", [])]
    candidate_ids = [item.get("id") for item in case.get("candidates", [])]
    event_ids = [item.get("id") for item in case.get("events", [])]
    for label, values in (("exits.id", exit_ids), ("groups.id", group_ids), ("candidates.id", candidate_ids), ("events.id", event_ids)):
        if None in values or len(values) != len(set(values)):
            missing.append(label)
    if case.get("candidates") and len(case["candidates"]) < 3:
        missing.append("candidates.min_3")
    max_ticks = int(event.get("max_ticks", 0) or 0)
    for index, exit_item in enumerate(case.get("exits", [])):
        if int(exit_item.get("capacity_per_tick", -1)) < 0 or int(exit_item.get("safe_queue", 0)) <= 0:
            missing.append(f"exits[{index}].capacity")
    for index, incident in enumerate(case.get("events", [])):
        if incident.get("exit_id") not in exit_ids:
            missing.append(f"events[{index}].exit_id")
        if not 0 <= float(incident.get("capacity_multiplier", -1)) <= 1:
            missing.append(f"events[{index}].capacity_multiplier")
        if not (1 <= int(incident.get("start_tick", 0)) <= int(incident.get("end_tick", 0)) <= max_ticks):
            missing.append(f"events[{index}].tick_window")
    for ci, candidate in enumerate(case.get("candidates", [])):
        prefs = candidate.get("preferences", {})
        if set(prefs) != set(group_ids):
            missing.append(f"candidates[{ci}].preferences.groups")
        for gid, choices in prefs.items():
            if not choices or not set(choices).issubset(set(exit_ids)):
                missing.append(f"candidates[{ci}].preferences.{gid}")
    return missing


def active_events(case: dict[str, Any], tick: int, event_ids: list[str]) -> list[dict[str, Any]]:
    selected = set(event_ids)
    return [
        event
        for event in case["events"]
        if event["id"] in selected and event["start_tick"] <= tick <= event["end_tick"]
    ]


def exit_capacities(case: dict[str, Any], tick: int, event_ids: list[str]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    caps = {item["id"]: int(item["capacity_per_tick"]) for item in case["exits"]}
    events = active_events(case, tick, event_ids)
    for event in events:
        exit_id = event["exit_id"]
        caps[exit_id] = int(round(caps[exit_id] * float(event["capacity_multiplier"])))
    return caps, events


@dataclass(frozen=True)
class GroupIntent:
    agent_id: str
    session_id: str
    tick: int
    group_id: str
    released: int
    target_exit: str
    worker_thread: str


@dataclass
class AgentContext:
    agent_id: str
    session_id: str
    group_id: str
    history: list[dict[str, Any]]
    inbox: list[dict[str, Any]]

    def submit_intent(self, *, tick: int, released: int, target: str) -> GroupIntent:
        if self.history and tick <= self.history[-1]["tick"]:
            raise ValueError("STALE_TICK")
        record = {"tick": tick, "released": released, "target": target}
        self.history.append(record)
        return GroupIntent(self.agent_id, self.session_id, tick, self.group_id, released, target, threading.current_thread().name)


def _group_intent(context: AgentContext, group: dict[str, Any], state: dict[str, Any], target: str, tick: int, barrier: threading.Barrier) -> GroupIntent:
    barrier.wait(timeout=3)
    remaining = int(state["origin_remaining"][group["id"]])
    released = min(remaining, int(group["release_per_tick"]))
    return context.submit_intent(tick=tick, released=released, target=target)


def _choose_alt(
    preferences: list[str],
    current: str,
    caps: dict[str, int],
    queue_totals: dict[str, int],
    safe_queues: dict[str, int],
) -> str:
    candidates = [eid for eid in preferences if eid != current and caps[eid] > 0]
    if not candidates:
        candidates = [eid for eid, cap in caps.items() if eid != current and cap > 0]
    if not candidates:
        return current
    return min(candidates, key=lambda eid: (queue_totals[eid] / safe_queues[eid], -caps[eid], eid))


def _allocate_capacity(queue_by_exit: dict[str, dict[str, int]], capacities: dict[str, int]) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    served: dict[str, dict[str, int]] = {eid: {} for eid in queue_by_exit}
    totals: dict[str, int] = {}
    for exit_id, group_queues in queue_by_exit.items():
        cap = capacities[exit_id]
        total = sum(group_queues.values())
        totals[exit_id] = min(cap, total)
        left = min(cap, total)
        order = sorted(group_queues)
        while left > 0 and any(group_queues[gid] > 0 for gid in order):
            active = [gid for gid in order if group_queues[gid] > 0]
            share = max(1, left // len(active))
            for gid in active:
                take = min(group_queues[gid], share, left)
                group_queues[gid] -= take
                served[exit_id][gid] = served[exit_id].get(gid, 0) + take
                left -= take
                if left <= 0:
                    break
    return served, totals


def simulate_candidate(
    case: dict[str, Any],
    candidate_id: str,
    event_ids: list[str] | None = None,
) -> dict[str, Any]:
    if case.get("task_type") != "large_event_egress_simulation":
        return {
            "decision": "NOT_APPLICABLE",
            "reason": "当前请求不是大型活动散场方案推演，Skill 不触发。",
            "skill": skill_evidence(),
        }
    missing = validate_case(case)
    if missing:
        return {"decision": "NEEDS_INPUT", "missing": missing, "skill": skill_evidence()}

    policy = load_policy()
    candidate = next(item for item in case["candidates"] if item["id"] == candidate_id)
    event_ids = event_ids if event_ids is not None else [event["id"] for event in case["events"]]
    known_event_ids = {event["id"] for event in case["events"]}
    unknown_events = sorted(set(event_ids) - known_event_ids)
    if unknown_events:
        return {"decision": "NEEDS_INPUT", "missing": [f"unknown_event:{item}" for item in unknown_events], "skill": skill_evidence()}
    exit_ids = [item["id"] for item in case["exits"]]
    safe_queues = {item["id"]: int(item["safe_queue"]) for item in case["exits"]}
    state = {
        "origin_remaining": {item["id"]: int(item["people"]) for item in case["groups"]},
        "queues": {eid: {item["id"]: 0 for item in case["groups"]} for eid in exit_ids},
        "completed": 0,
        "targets": {gid: prefs[0] for gid, prefs in candidate["preferences"].items()},
    }
    trace: list[dict[str, Any]] = []
    replans: list[dict[str, Any]] = []
    overflow_ticks = 0
    max_density = 0.0
    unique_threads: set[str] = set()
    session_id = f"session-{case['case_id']}-{candidate_id}-{stable_digest(event_ids)[:8]}"
    contexts = {
        group["id"]: AgentContext(
            agent_id=f"group-agent-{group['id']}",
            session_id=session_id,
            group_id=group["id"],
            history=[],
            inbox=[],
        ) for group in case["groups"]
    }
    previous_state_hash = stable_digest({"session_id": session_id, "state": state})
    actual_clearance_tick: int | None = None

    for tick in range(1, int(case["event"]["max_ticks"]) + 1):
        caps, events = exit_capacities(case, tick, event_ids)
        queue_totals = {eid: sum(state["queues"][eid].values()) for eid in exit_ids}

        # A local replan edits only the virtual candidate state. It does not
        # issue venue instructions or write a production map policy.
        if candidate["replan_mode"] != "none":
            trigger = float(policy["replan_trigger_density"])
            if candidate["replan_mode"] == "late":
                trigger = 1.05
            for group in case["groups"]:
                gid = group["id"]
                current = state["targets"][gid]
                density = queue_totals[current] / safe_queues[current]
                if caps[current] == 0 or density >= trigger:
                    alt = _choose_alt(candidate["preferences"][gid], current, caps, queue_totals, safe_queues)
                    if alt != current:
                        ratio = min(float(candidate["reroute_ratio"]), float(policy["max_replan_share_per_tick"]))
                        movable = int(round(state["queues"][current][gid] * ratio))
                        state["queues"][current][gid] -= movable
                        state["queues"][alt][gid] += movable
                        state["targets"][gid] = alt
                        queue_totals[current] -= movable
                        queue_totals[alt] += movable
                        replans.append({
                            "tick": tick,
                            "agent": "局部重规划 Agent",
                            "group_id": gid,
                            "from": current,
                            "to": alt,
                            "moved_virtual_queue": movable,
                            "reason": "EXIT_CLOSED" if caps[current] == 0 else "QUEUE_DENSITY",
                        })

        barrier = threading.Barrier(len(case["groups"]))
        with ThreadPoolExecutor(max_workers=len(case["groups"]), thread_name_prefix=f"crowd-t{tick}") as pool:
            futures = [
                pool.submit(_group_intent, contexts[group["id"]], group, state, state["targets"][group["id"]], tick, barrier)
                for group in case["groups"]
            ]
            intents = [future.result() for future in futures]

        for intent in intents:
            unique_threads.add(intent.worker_thread)
            state["origin_remaining"][intent.group_id] -= intent.released
            state["queues"][intent.target_exit][intent.group_id] += intent.released

        served, served_totals = _allocate_capacity(state["queues"], caps)
        state["completed"] += sum(served_totals.values())
        queue_totals = {eid: sum(state["queues"][eid].values()) for eid in exit_ids}
        densities = {eid: round(queue_totals[eid] / safe_queues[eid], 3) for eid in exit_ids}
        tick_max_density = max(densities.values())
        max_density = max(max_density, tick_max_density)
        if tick_max_density > float(policy["max_queue_density_ratio"]):
            overflow_ticks += 1
        input_hash = stable_digest({"previous": previous_state_hash, "tick": tick, "capacities": caps, "state": state})
        output_hash = stable_digest({"input_hash": input_hash, "state": state, "queue": queue_totals})
        trace.append({
            "tick": tick,
            "minute": tick * int(case["event"]["tick_minutes"]),
            "active_events": [event["id"] for event in events],
            "capacities": caps,
            "released": {intent.group_id: intent.released for intent in intents},
            "targets": deepcopy(state["targets"]),
            "served": served_totals,
            "queue": queue_totals,
            "density": densities,
            "completed": state["completed"],
            "remaining": sum(state["origin_remaining"].values()) + sum(queue_totals.values()),
            "worker_threads": sorted({intent.worker_thread for intent in intents}),
            "agent_ids": sorted(intent.agent_id for intent in intents),
            "session_id": session_id,
            "previous_state_hash": previous_state_hash,
            "input_state_hash": input_hash,
            "output_state_hash": output_hash,
        })
        previous_state_hash = output_hash
        if actual_clearance_tick is None and state["completed"] == int(case["event"]["audience_count"]):
            actual_clearance_tick = tick

    audience = int(case["event"]["audience_count"])
    rate = state["completed"] / audience
    gates = {
        "clearance_rate": rate >= float(policy["min_clearance_rate"]),
        "queue_density": max_density <= float(policy["max_queue_density_ratio"]),
        "overflow_ticks": overflow_ticks <= int(policy["max_overflow_ticks"]),
        "permission": True,
    }
    signable = all(gates.values())
    result: dict[str, Any] = {
        "run_id": f"run-{case['case_id']}-{candidate_id}-{stable_digest(event_ids)[:8]}",
        "case_id": case["case_id"],
        "candidate": deepcopy(candidate),
        "event_ids": event_ids,
        "decision": "SIGNABLE_CANDIDATE" if signable else "NOT_SIGNABLE",
        "metrics": {
            "completed_people": state["completed"],
            "audience_count": audience,
            "clearance_rate": round(rate, 4),
            "clearance_minutes": (actual_clearance_tick or int(case["event"]["max_ticks"])) * int(case["event"]["tick_minutes"]),
            "remaining_people": audience - state["completed"],
            "max_queue_density_ratio": round(max_density, 3),
            "overflow_ticks": overflow_ticks,
            "local_replans": len(replans),
        },
        "gates": gates,
        "trace": trace,
        "replans": replans,
        "parallel_evidence": {
            "agent_count_per_tick": len(case["groups"]),
            "unique_worker_threads": sorted(unique_threads),
            "fan_out_before_capacity_fan_in": True,
            "session_id": session_id,
            "agent_contexts": [
                {"agent_id": context.agent_id, "group_id": context.group_id, "history_length": len(context.history), "inbox_size": len(context.inbox)}
                for context in contexts.values()
            ],
        },
        "skill": skill_evidence(),
        "permission_boundary": {
            "virtual_candidate_only": True,
            "human_signature_required": True,
            "real_world_execution_allowed": False,
        },
    }
    result["evidence_digest"] = stable_digest({key: value for key, value in result.items() if key != "evidence_digest"})
    return result


def verify_result(result: dict[str, Any]) -> bool:
    claimed = result.get("evidence_digest")
    body = {key: value for key, value in result.items() if key != "evidence_digest"}
    if claimed != stable_digest(body):
        return False
    metrics = result.get("metrics", {})
    policy = load_policy()
    expected = {
        "clearance_rate": metrics.get("clearance_rate", 0) >= float(policy["min_clearance_rate"]),
        "queue_density": metrics.get("max_queue_density_ratio", 99) <= float(policy["max_queue_density_ratio"]),
        "overflow_ticks": metrics.get("overflow_ticks", 99) <= int(policy["max_overflow_ticks"]),
        "permission": result.get("permission_boundary", {}).get("real_world_execution_allowed") is False,
    }
    return expected == result.get("gates") and result.get("skill") == skill_evidence()


def verify_bundle(bundle: dict[str, Any]) -> bool:
    claimed = bundle.get("evidence_digest")
    body = {key: value for key, value in bundle.items() if key != "evidence_digest"}
    return claimed == stable_digest(body) and all(verify_result(result) for result in bundle.get("results", []))


def run_all_candidates(case: dict[str, Any] | None = None, event_ids: list[str] | None = None) -> dict[str, Any]:
    case = deepcopy(case or load_case())
    results = [simulate_candidate(case, item["id"], event_ids) for item in case["candidates"]]
    signable = [item for item in results if item["decision"] == "SIGNABLE_CANDIDATE"]
    recommended = min(
        signable,
        key=lambda item: (
            item["metrics"]["max_queue_density_ratio"],
            item["metrics"]["clearance_minutes"],
            item["candidate"]["id"],
        ),
        default=None,
    )
    payload = {
        "case_id": case["case_id"],
        "event_ids": event_ids if event_ids is not None else [event["id"] for event in case["events"]],
        "results": results,
        "recommended_candidate_id": recommended["candidate"]["id"] if recommended else None,
        "decision": "READY_FOR_HUMAN_REVIEW" if recommended else "REPLAN_REQUIRED",
        "skill": skill_evidence(),
    }
    payload["evidence_digest"] = stable_digest({key: value for key, value in payload.items() if key != "evidence_digest"})
    return payload


def baseline(case: dict[str, Any] | None = None) -> dict[str, Any]:
    result = simulate_candidate(deepcopy(case or load_case()), "A")
    result["baseline_label"] = "V0：静态最近出口分配"
    result["first_divergence"] = "第 4 轮东门地铁入口关闭后，客群仍按原出口释放，系统没有局部重规划。"
    return result


def overcorrected(case: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(case or load_case())
    payload["candidates"].append({
        "id": "X",
        "name": "单出口兜底",
        "description": "看到东门关闭后，把全部客群统一改到南门；保留的过度修正坏例。",
        "replan_mode": "none",
        "reroute_ratio": 0.0,
        "preferences": {group["id"]: ["E2"] for group in payload["groups"]},
    })
    result = simulate_candidate(payload, "X")
    result["baseline_label"] = "V0.5：把全部客群挤到唯一备用出口"
    result["first_divergence"] = "第 1 轮所有客群同时指向南门，局部故障被放大成新的单点拥堵。"
    return result


def approve(run_bundle: dict[str, Any], candidate_id: str, approver: str, note: str) -> dict[str, Any]:
    if not verify_bundle(run_bundle):
        raise ValueError("证据包校验失败，拒绝签发")
    if not approver.strip() or not note.strip():
        raise ValueError("签发人和签发说明不能为空")
    result = next((item for item in run_bundle["results"] if item["candidate"]["id"] == candidate_id), None)
    if not result:
        raise ValueError("候选不存在")
    if result["decision"] != "SIGNABLE_CANDIDATE":
        raise ValueError("当前候选未通过能力与风险门禁，不能签发")
    if not verify_result(result):
        raise ValueError("候选证据校验失败，拒绝签发")
    signature_basis = {
        "bundle": run_bundle["evidence_digest"],
        "candidate": candidate_id,
        "approver": approver.strip(),
        "note": note.strip(),
    }
    return {
        "approval_id": f"approval-{stable_digest(signature_basis)[:12]}",
        "result_version": "signed-plan@1",
        "decision": "HUMAN_SIGNED",
        "candidate_id": candidate_id,
        "candidate_name": result["candidate"]["name"],
        "approver": approver.strip(),
        "note": note.strip(),
        "evidence_digest": result["evidence_digest"],
        "next_owner": "获得授权的现场运营与交通协同系统",
        "execution_performed": False,
    }


def attempt_real_world_execution() -> dict[str, Any]:
    return {
        "decision": "EXTERNAL_AUTHORITY_REQUIRED",
        "allowed": False,
        "message": "本系统只能签发建议包，不能执行封路、运力调度或公众引导。",
    }


if __name__ == "__main__":
    print(json.dumps(run_all_candidates(), ensure_ascii=False, indent=2))
