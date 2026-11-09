"""Monitoring from redacted traces: one summary function and one alert rule evaluator."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "monitoring_rules.json"

# A run "errors" when the system failed, not when it correctly refused or abstained.
ERROR_STOP_REASONS = frozenset({"provider_error", "timeout", "turn_limit", "tool_limit"})


def p95(values: list[int]) -> int:
    """Nearest-rank 95th percentile; 0 when there is no data."""
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    run_count = len(traces)
    errors = sum(
        1 for t in traces
        if t.get("stop_reason") in ERROR_STOP_REASONS
        or t.get("error")
        or any(call.get("status") == "error" for call in t.get("tool_calls", []))
    )
    all_calls = [call for t in traces for call in t.get("tool_calls", [])]
    outcomes: dict[str, int] = {}
    for t in traces:
        outcomes[t.get("outcome", "unknown")] = outcomes.get(t.get("outcome", "unknown"), 0) + 1
    return {
        "run_count": run_count,
        "error_rate": round(errors / run_count, 4) if run_count else 0.0,
        "p95_latency_ms": p95([int(t.get("usage", {}).get("latency_ms", 0)) for t in traces]),
        "tool_calls": len(all_calls),
        "blocked_tool_calls": sum(1 for call in all_calls if call.get("status") == "blocked"),
        "outcomes": outcomes,
    }


def load_rules(path: Path = RULES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


OPERATORS = {
    "gt": lambda value, threshold: value > threshold,
    "gte": lambda value, threshold: value >= threshold,
    "lt": lambda value, threshold: value < threshold,
    "lte": lambda value, threshold: value <= threshold,
}


def evaluate_alerts(summary: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Active alerts only. A rule never fires below its minimum_samples: 1 slow run out of 1 is noise."""
    active = []
    for rule in rules:
        if summary["run_count"] < rule.get("minimum_samples", 0):
            continue
        value = summary[rule["metric"]]
        if OPERATORS[rule["operator"]](value, rule["threshold"]):
            active.append({
                "rule_id": rule["rule_id"],
                "metric": rule["metric"],
                "value": value,
                "threshold": rule["threshold"],
                "samples": summary["run_count"],
                "owner": rule["owner"],
                "response": rule["response"],
            })
    return active
