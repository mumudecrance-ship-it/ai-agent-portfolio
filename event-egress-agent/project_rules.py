from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import map_engine
from live_agent import LiveAgentError


ALLOWED_KINDS = {"RAIN", "EXIT_CLOSED", "CAPACITY_CHANGE", "TRANSIT_CLOSED"}


def preflight_live(payload: dict[str, Any]) -> None:
    """Reject invalid local venue data before spending a real API request."""
    try:
        map_engine.build_case_from_venue(payload.get("venue_config") or {})
    except (TypeError, ValueError) as exc:
        raise LiveAgentError("VENUE_PROFILE_REJECTED", str(exc), "修正场馆名称、人数或出口配置后重试。") from exc
    event_description = str(payload.get("event_description") or "").strip()
    if len(event_description) < 8:
        raise LiveAgentError("API_INPUT_REQUIRED", "事件描述还不足 8 个字。", "可以自由描述事件，或明确写‘本轮无突发事件’。")


def _venue_summary(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": case["event"]["venue"],
        "audience_count": case["event"]["audience_count"],
        "tick_minutes": case["event"]["tick_minutes"],
        "max_ticks": case["event"]["max_ticks"],
        "zone_notes": case.get("personal_profile", {}).get("zone_notes", ""),
        "groups": [
            {"id": item["id"], "name": item["name"], "people": item["people"]}
            for item in case["groups"]
        ],
        "exits": [
            {
                "id": item["id"],
                "name": item["name"],
                "direction": item.get("direction", ""),
                "capacity_per_tick": item["capacity_per_tick"],
                "safe_queue": item["safe_queue"],
                "x": item.get("x"),
                "y": item.get("y"),
            }
            for item in case["exits"]
        ],
    }


def run_fixed(result: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    case = map_engine.load_case()
    if result["id"] == "baseline":
        computed = map_engine.baseline(case)
        candidate_results = [{"candidate": "A", "name": "就近优先", "decision": computed["decision"], "metrics": computed["metrics"]}]
    elif result["id"] == "overcorrected":
        computed = map_engine.overcorrected(case)
        candidate_results = [{"candidate": "X", "name": "单出口过度修正", "decision": computed["decision"], "metrics": computed["metrics"]}]
    else:
        bundle = map_engine.run_all_candidates(case)
        computed = next(item for item in bundle["results"] if item["candidate"]["id"] == "B")
        candidate_results = [
            {
                "candidate": item["candidate"]["id"],
                "name": item["candidate"]["name"],
                "decision": item["decision"],
                "metrics": item["metrics"],
            }
            for item in bundle["results"]
        ]
    return {
        **result,
        "metrics": computed["metrics"],
        "source": "FIXED_REGRESSION_DETERMINISTIC",
        "mode_note": "固定案例只回放确定性引擎，本轮没有调用模型。",
        "venue_profile": _venue_summary(case),
        "computed": computed,
        "candidate_results": candidate_results,
        "agent_trace": [
            {"role": "AGENT", "label": "回放编排器读取固定场馆与事件"},
            {"role": "SKILL", "label": "加载散场推演门禁"},
            {"role": "RULE", "label": "校验场馆、事件和候选共享同一份输入"},
            {"role": "ENGINE", "label": "World Simulator 单线程结算 12 轮"},
            {"role": "HUMAN", "label": "生成待人工确认候选"},
        ],
        "evidence_digest": computed.get("evidence_digest"),
    }


def validate_live(result: dict[str, Any], payload: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    if result.get("interpretation_status") != "READY":
        raise LiveAgentError(
            "API_NEEDS_CLARIFICATION",
            result.get("summary") or "AI 认为这段事件描述还不足以进入仿真。",
            "补充受影响的出口、大致开始/结束轮次和容量变化程度。",
        )
    try:
        case = map_engine.build_case_from_venue(payload.get("venue_config") or {})
    except (TypeError, ValueError) as exc:
        raise LiveAgentError("VENUE_PROFILE_REJECTED", str(exc), "修正场馆名称、人数或出口配置后重试。") from exc

    exit_ids = {item["id"] for item in case["exits"]}
    group_ids = {item["id"] for item in case["groups"]}
    changes = result.get("changes")
    if not isinstance(changes, list):
        raise LiveAgentError("API_RESPONSE_INVALID", "AI 返回的 changes 不是列表。", "重新运行实时 Agent。")
    for item in changes:
        if not isinstance(item, dict):
            raise LiveAgentError("API_RESPONSE_INVALID", "变化草案中出现了非对象项。", "重新运行实时 Agent。")
        target, kind = str(item.get("target") or "").upper(), item.get("kind")
        start, end = item.get("start_step"), item.get("end_step")
        value = item.get("value")
        item["target"] = target
        if target not in exit_ids:
            raise LiveAgentError("API_SCOPE_REJECTED", f"AI 引用了不存在的出口 {target or '—'}。", f"只能使用当前场馆的出口：{', '.join(sorted(exit_ids))}。")
        if kind not in ALLOWED_KINDS:
            raise LiveAgentError("API_SCOPE_REJECTED", "变化类型不在本项目允许范围。", "使用降雨、出口关闭、容量变化或接驳暂停。")
        if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= 12:
            raise LiveAgentError("API_SCOPE_REJECTED", "变化轮次必须在 1—12 之间，且开始不能晚于结束。", "在事件描述中给出大致的轮次范围。")
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise LiveAgentError("API_SCOPE_REJECTED", "容量乘数必须在 0—1 之间。", "例如‘剩一半’应整理为 0.5。")
        if kind in {"EXIT_CLOSED", "TRANSIT_CLOSED"} and float(value) != 0:
            raise LiveAgentError("API_SCOPE_REJECTED", "关闭类变化的容量乘数必须为 0。", "重新运行并检查事件描述。")

    intents = result.get("local_intents")
    if not isinstance(intents, list):
        raise LiveAgentError("API_RESPONSE_INVALID", "AI 返回的 local_intents 不是列表。", "重新运行实时 Agent。")
    for intent in intents:
        if not isinstance(intent, dict):
            raise LiveAgentError("API_RESPONSE_INVALID", "局部意图中出现了非对象项。", "重新运行实时 Agent。")
        group_id = str(intent.get("group_id") or "").upper()
        target_exit = str(intent.get("target_exit") or "").upper()
        intent["group_id"] = group_id
        intent["target_exit"] = target_exit
        if group_id and group_id not in group_ids:
            raise LiveAgentError("API_SCOPE_REJECTED", f"AI 引用了不存在的客群 {group_id}。", f"只能使用：{', '.join(sorted(group_ids))}。")
        if target_exit not in exit_ids:
            raise LiveAgentError("API_SCOPE_REJECTED", f"AI 意图指向了不存在的出口 {target_exit or '—'}。", f"只能使用：{', '.join(sorted(exit_ids))}。")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    preview = {
        "preview_id": f"live-{int(now.timestamp())}",
        "mode": "API_PREVIEW",
        "adapter_status": "OK",
        "live_request": True,
        "requires_human_confirmation": True,
        "observed_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "changes": changes,
    }
    try:
        updated, event_ids = map_engine.apply_live_preview(case, preview)
        bundle = map_engine.run_all_candidates(updated, event_ids=event_ids)
    except ValueError as exc:
        raise LiveAgentError("RULE_REJECTED", str(exc), "修正变化草案后重新仿真。") from exc

    recommended = next((item for item in bundle["results"] if item["candidate"]["id"] == bundle["recommended_candidate_id"]), None)
    trace = recommended["trace"] if recommended else []
    metrics = recommended["metrics"] if recommended else {}
    return {
        "summary": f"变化理解草案：{result.get('summary') or '已整理本轮输入。'}",
        "decision": "PENDING_HUMAN_CONFIRMATION" if recommended else "REPLAN_REQUIRED",
        "source": "LIVE_API_PLUS_DETERMINISTIC_ENGINE",
        "venue_profile": _venue_summary(updated),
        "changes": changes,
        "local_intents": intents,
        "recommended_candidate": bundle["recommended_candidate_id"],
        "metrics": metrics,
        "candidate_results": [
            {
                "candidate": item["candidate"]["id"],
                "name": item["candidate"]["name"],
                "decision": item["decision"],
                "metrics": item["metrics"],
            }
            for item in bundle["results"]
        ],
        "recommended_trace": trace,
        "rule_checks": {
            "venue_profile_valid": True,
            "targets_exist_in_submitted_venue": True,
            "steps_in_1_to_12": True,
            "values_in_0_to_1": True,
            "deterministic_simulator_ran": True,
            "real_world_execution_allowed": False,
            "event_ids": event_ids,
        },
        "agent_trace": [
            {"role": "AGENT", "label": "真实 API 返回变化草案与局部意图"},
            {"role": "SKILL", "label": "simulate-event-egress-plan 加载门禁"},
            {"role": "RULE", "label": "校验出口、轮次、容量乘数与权限"},
            {"role": "ENGINE", "label": "确定性引擎复算 A/B/C 的 12 轮"},
            {"role": "HUMAN", "label": "候选留在本地，等待具名确认"},
        ],
        "handoff_boundary": {
            "current_status": "LOCAL_SIMULATION_CANDIDATE",
            "next_owner": "当前使用者",
            "external_boundary": project["boundaries"]["stop_at"],
        },
        "evidence_digest": bundle["evidence_digest"],
    }
