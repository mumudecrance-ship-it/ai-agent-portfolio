#!/usr/bin/env python3
import json
from pathlib import Path
import sys


REQUIRED = [
    "metric_name", "numerator", "denominator", "window", "required_events",
    "data_source", "not_success", "target", "business_guardrails",
    "permission_guardrail", "expand_rule", "rollback_rule", "result"
]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_metric_contract.py <metric-contract.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED if key not in payload]
    errors = list(missing)
    if payload.get("result") not in (None, ""):
        errors.append("result_must_not_be_prefilled")
    if not payload.get("required_events"):
        errors.append("required_events")
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)
