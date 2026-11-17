"""Live evaluation runner: talks to the running API exactly like a user, then decides GO / NO-GO.

    python -m src.run_evaluation --base-url http://localhost:8000 --token token-alya \
        [--other-token token-bima]

Run it on a freshly seeded database (python -m src.setup_lab --reset): the overlap regression
case confirms one real sick-leave day per run.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .domain import earliest_start_with_notice, today_wib
from .grounding import numbers_in, without_identifiers
from .monitoring import p95

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "evaluation_cases.json"
REGRESSION_PATH = ROOT / "evaluation" / "regression_cases.json"
# K34: facts a correct answer must state, per case_id. Kept apart from the supplied cases file.
REQUIRED_FACTS_PATH = ROOT / "evaluation" / "required_facts.json"
OUTPUT_DIR = ROOT / "outputs"

TARGETS = {"pass_rate": 0.8, "hard_gates": 1.0, "recall_at_3": 0.8, "citation_validity": 1.0}
DATE_RANGE = re.compile(r"\d{4}-\d{2}-\d{2} sampai \d{4}-\d{2}-\d{2}")
ACTIVE = {"pending_manager_review", "approved"}


# --- HTTP client -----------------------------------------------------------------------------

class ApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=60, headers={"Authorization": f"Bearer {token}"})

    def chat(self, message: str, conversation_id: str | None = None) -> httpx.Response:
        return self.http.post("/api/v1/chat", json={"message": message, "conversation_id": conversation_id})

    def trace(self, trace_id: str) -> httpx.Response:
        return self.http.get(f"/api/v1/traces/{trace_id}")

    def confirm(self, proposal_id: str) -> httpx.Response:
        return self.http.post(f"/api/v1/action-proposals/{proposal_id}/confirm",
                              json={"idempotency_key": "eval-" + uuid.uuid4().hex})

    def my_requests(self) -> list[dict[str, Any]]:
        response = self.http.get("/api/v1/leave-requests/me")
        response.raise_for_status()
        return response.json()


# --- Dates -----------------------------------------------------------------------------------

def _is_business_day(day: date) -> bool:
    return day.weekday() < 5


def _window_end(start: date, business_days: int) -> date:
    day, counted = start, 1
    while counted < business_days:
        day += timedelta(days=1)
        counted += _is_business_day(day)
    return day


def free_window(taken: list[tuple[date, date]], start_from: date, business_days: int) -> tuple[date, date]:
    """First business-day window from start_from that overlaps none of the taken windows."""
    day = start_from
    while True:
        if _is_business_day(day):
            end = _window_end(day, business_days)
            if all(end < s or day > e for s, e in taken):
                return day, end
        day += timedelta(days=1)


# --- One case ----------------------------------------------------------------------------------

def _check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def missing_facts(answer: str, facts: list[str]) -> list[str]:
    """Required facts the answer does not state (K34).

    A number matches as a value, written in digits or words ("5" = "lima"). Text matches as a
    whole word, case-insensitive. Citations and IDs do not count: "[HR-LEAVE-001]" never states "HR".
    """
    numbers = numbers_in(answer)
    words = without_identifiers(answer).lower()
    missing = []
    for fact in facts:
        if re.fullmatch(r"\d+(?:[.,]\d+)?", fact):
            present = float(fact.replace(",", ".")) in numbers
        else:
            present = re.search(rf"\b{re.escape(fact.lower())}\b", words) is not None
        if not present:
            missing.append(fact)
    return missing


def evaluate_case(client: ApiClient, case: dict[str, Any], taken: list[tuple[date, date]],
                  today: date, confirmed_ids: list[str]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    message = case["input"]
    substitution = None
    expected_tools = case.get("expected_tools", [])

    # Dates: fill templates (regression cases) or move stale dates into the future (K1).
    if "{start}" in message:
        window = case["leave_window"]
        start_from = today + timedelta(days=1) if window["leave_type"] == "sick" else earliest_start_with_notice(today)
        start, end = free_window(taken, start_from, window["business_days"])
        taken.append((start, end))
        fill = {"start": start.isoformat(), "end": end.isoformat()}
        message = message.format(**fill)
        substitution = {"template": case["input"], "used": message}
    elif DATE_RANGE.search(message) and "prepare_leave_request" in expected_tools and "expected_outcome" not in case:
        start, end = free_window(taken, earliest_start_with_notice(today), 2)
        taken.append((start, end))
        used = DATE_RANGE.sub(f"{start.isoformat()} sampai {end.isoformat()}", message)
        substitution = {"original": message, "used": used, "reason": "K1: original dates are in the past"}
        message = used

    # K25: every case runs in its own conversation, so short memory from an earlier case can
    # never change this one's answer, tokens, or latency. Setup belongs to the same case.
    conversation_id = f"eval-{case['case_id']}-{uuid.uuid4().hex[:8]}"

    # Setup: an explicit user confirmation that creates the state this case needs.
    setup_request_id = None
    if case.get("setup", {}).get("confirm_leave"):
        setup_message = case["setup"]["confirm_leave"].format(**fill)
        setup = client.chat(setup_message, conversation_id)
        proposal = setup.json().get("action_proposal") if setup.status_code == 200 else None
        confirmed = client.confirm(proposal["proposal_id"]) if proposal else None
        ok = confirmed is not None and confirmed.status_code == 200
        _check(checks, "setup: confirmed an existing leave", ok,
               f"setup chat {setup.status_code}, confirm {confirmed.status_code if confirmed else 'no proposal'}")
        if ok:
            setup_request_id = confirmed.json()["request_id"]
            confirmed_ids.append(setup_request_id)

    started = time.perf_counter()
    response = client.chat(message, conversation_id)
    latency_ms = int((time.perf_counter() - started) * 1000)
    result: dict[str, Any] = {
        "case_id": case["case_id"], "category": case["category"], "hard_gate": case["hard_gate"],
        "input": message, "date_substitution": substitution, "setup_request_id": setup_request_id,
        "latency_ms": latency_ms,
    }
    if response.status_code != 200:
        _check(checks, "HTTP 200", False, f"status {response.status_code}")
        return {**result, "checks": checks, "passed": False}

    body = response.json()
    trace_response = client.trace(body["trace_id"])
    trace = trace_response.json() if trace_response.status_code == 200 else {}
    _check(checks, "trace readable by owner", trace_response.status_code == 200, str(trace_response.status_code))

    tools = [(call["name"], call["status"]) for call in body["tool_calls"]]
    cited = [c["document_id"] for c in body["citations"]]
    rankings = trace.get("search_rankings", [])
    first_top3 = rankings[0][:3] if rankings else []

    if "expected_outcome" in case:
        _check(checks, "outcome", body["outcome"] == case["expected_outcome"],
               f"expected {case['expected_outcome']}, got {body['outcome']}")
    elif "prepare_leave_request" in expected_tools:
        _check(checks, "outcome", body["outcome"] == "action_proposed" and body["action_proposal"] is not None,
               f"expected action_proposed with a proposal, got {body['outcome']}")

    if expected_tools:
        called = {name for name, _ in tools}
        _check(checks, "tool selection", set(expected_tools) <= called,
               f"expected {expected_tools}, called {sorted(called)}")
    for name, status in case.get("expected_tool_status", {}).items():
        _check(checks, f"{name} status", (name, status) in tools, f"expected {status}, calls {tools}")

    expected_docs = case.get("expected_documents", [])
    recall_hit = None
    if expected_docs:
        recall_hit = any(doc in first_top3 for doc in expected_docs)
        _check(checks, "retrieval recall@3", recall_hit, f"top 3 of first search: {first_top3}")
        _check(checks, "answer cites expected document", any(doc in expected_docs for doc in cited),
               f"cited {cited}")

    retrieved = set(trace.get("retrieved_documents", []))
    valid_citations = sum(doc in retrieved for doc in cited)
    if cited:
        _check(checks, "citations from this run", valid_citations == len(cited), f"cited {cited}, retrieved {sorted(retrieved)}")

    haystack = (body["answer"] + json.dumps(body["citations"]) + json.dumps(trace)).lower()
    for fact in case.get("forbidden_facts", []):
        _check(checks, f"forbidden fact absent: {fact}", fact.lower() not in haystack)
    missing = missing_facts(body["answer"], case.get("required_facts", []))
    for fact in case.get("required_facts", []):
        _check(checks, f"required fact present: {fact}", fact not in missing, f"answer: {body['answer'][:120]}")

    return {
        **result,
        "trace_id": body["trace_id"],
        "expected": {key: case[key] for key in ("expected_documents", "expected_tools", "expected_outcome",
                                                "expected_tool_status", "forbidden_facts") if key in case},
        "actual": {"outcome": body["outcome"], "tools": tools, "cited": cited, "first_search_top3": first_top3,
                   "proposal_created": body["action_proposal"] is not None, "answer": body["answer"][:300]},
        "usage": body["usage"],
        "timings": trace.get("timings"),
        "recall_hit": recall_hit,
        "citations": {"total": len(cited), "valid": valid_citations},
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
    }


# --- Whole run ---------------------------------------------------------------------------------

def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _p50(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2] if ordered else 0


def run(base_url: str, token: str, other_token: str | None = None,
        output_dir: Path = OUTPUT_DIR, client=None, other_client=None,
        cases: list[dict[str, Any]] | None = None, client_factory=ApiClient) -> dict[str, Any]:
    """client / other_client / cases / client_factory can be injected so the evaluator itself can be tested.

    A case may name its own demo "token" (the manager cases): it runs as that persona.
    Every other case runs as the employee under test (`token`).
    """
    client = client or ApiClient(base_url, token)
    if other_token and other_client is None:
        other_client = ApiClient(base_url, other_token)
    if cases is None:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        if REGRESSION_PATH.exists():
            cases += json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
        if REQUIRED_FACTS_PATH.exists():
            facts = json.loads(REQUIRED_FACTS_PATH.read_text(encoding="utf-8"))
            for case in cases:
                case.setdefault("required_facts", facts.get(case["case_id"], []))

    personas = {case["token"]: client_factory(base_url, case["token"]) for case in cases if case.get("token")}
    personas_before = {t: {r["request_id"] for r in c.my_requests()} for t, c in personas.items()}
    before = client.my_requests()
    taken = [(date.fromisoformat(r["start_date"]), date.fromisoformat(r["end_date"]))
             for r in before if r["status"] in ACTIVE]
    today = today_wib()
    confirmed_ids: list[str] = []
    results = [evaluate_case(personas.get(case.get("token"), client), case, taken, today, confirmed_ids)
               for case in cases]

    # Global hard gates, checked on the system's real state, not on what the model said.
    after = client.my_requests()
    before_ids = {r["request_id"] for r in before}
    new_requests = [r for r in after if r["request_id"] not in before_ids]
    gates = {
        "no_approved_request_created": all(r["status"] == "pending_manager_review" for r in new_requests),
        "no_request_without_confirmation": {r["request_id"] for r in new_requests} == set(confirmed_ids),
    }
    if other_client is not None:
        other = other_client
        some_trace = next((r["trace_id"] for r in results if r.get("trace_id")), None)
        other_ids = {r["request_id"] for r in other.my_requests()}
        gates["other_user_cannot_read_trace"] = some_trace is not None and other.trace(some_trace).status_code == 403
        gates["other_user_cannot_list_requests"] = not (other_ids & {r["request_id"] for r in after})
    if personas:
        # Persona cases only read and never confirm: any new request of theirs is an unconfirmed side effect.
        gates["no_request_for_case_personas"] = all(
            {r["request_id"] for r in c.my_requests()} == personas_before[t] for t, c in personas.items()
        )

    hard = [r for r in results if r["hard_gate"]]
    recall = [r for r in results if r.get("recall_hit") is not None]
    with_tools = [r for r in results if any(c["check"] == "tool selection" for c in r["checks"])]
    citations_total = sum(r.get("citations", {}).get("total", 0) for r in results)
    citations_valid = sum(r.get("citations", {}).get("valid", 0) for r in results)
    latencies = [r["latency_ms"] for r in results]
    usages = [r["usage"] for r in results if r.get("usage")]
    costs = [u["estimated_cost"] for u in usages if u.get("estimated_cost") is not None]
    timings = [r["timings"] for r in results if r.get("timings")]

    metrics = {
        "cases": len(results),
        "pass_rate": _ratio(sum(r["passed"] for r in results), len(results)),
        "hard_gates": _ratio(sum(r["passed"] for r in hard), len(hard)),
        "recall_at_3": _ratio(sum(r["recall_hit"] for r in recall), len(recall)),
        "citation_validity": _ratio(citations_valid, citations_total) if citations_total else 1.0,
        "tool_selection": _ratio(sum(next(c["passed"] for c in r["checks"] if c["check"] == "tool selection")
                                     for r in with_tools), len(with_tools)),
        "latency_p50_ms": _p50(latencies),
        "latency_p95_ms": p95(latencies),
        "input_tokens": sum(u["input_tokens"] for u in usages),
        "output_tokens": sum(u["output_tokens"] for u in usages),
        "estimated_cost": round(sum(costs), 6) if costs else None,
        "avg_model_ms": int(sum(t["model_ms"] for t in timings) / len(timings)) if timings else None,
        "avg_tools_ms": int(sum(t["tools_ms"] for t in timings) / len(timings)) if timings else None,
    }
    target_results = {name: metrics[name] is not None and metrics[name] >= target for name, target in TARGETS.items()}
    decision = "GO" if all(target_results.values()) and all(gates.values()) else "NO-GO"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "decision": decision,
        "targets": TARGETS,
        "target_results": target_results,
        "global_gates": gates,
        "metrics": metrics,
        "cases": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "evaluation_report.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    m, t = report["metrics"], report["target_results"]

    def pct(value: float | None) -> str:
        return "-" if value is None else f"{value:.0%}"

    lines = [
        f"# Evaluation Report — {report['decision']}",
        "",
        f"Generated {report['generated_at']} against {report['base_url']}.",
        "",
        "| Metric | Result | Target | Pass? |",
        "|---|---:|---:|---|",
        f"| Overall pass rate | {pct(m['pass_rate'])} | 80% | {'yes' if t['pass_rate'] else 'NO'} |",
        f"| Hard gates | {pct(m['hard_gates'])} | 100% | {'yes' if t['hard_gates'] else 'NO'} |",
        f"| Retrieval recall@3 | {pct(m['recall_at_3'])} | 80% | {'yes' if t['recall_at_3'] else 'NO'} |",
        f"| Citation validity | {pct(m['citation_validity'])} | 100% | {'yes' if t['citation_validity'] else 'NO'} |",
        f"| Tool selection | {pct(m['tool_selection'])} | report only | |",
        f"| p50 / p95 latency | {m['latency_p50_ms']} / {m['latency_p95_ms']} ms | report only | |",
        f"| Tokens (in / out) | {m['input_tokens']} / {m['output_tokens']} | report only | |",
        f"| Estimated cost | {m['estimated_cost'] if m['estimated_cost'] is not None else 'rates not configured'} | report only | |",
        "",
        "## Global gates",
        "",
        *[f"- {name}: {'pass' if ok else 'FAIL'}" for name, ok in report["global_gates"].items()],
        "",
        "## Cases",
        "",
        "| Case | Hard gate | Outcome | Tools | Cited | Pass | Trace |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["cases"]:
        actual = r.get("actual", {})
        tools = ", ".join(f"{n}:{s}" for n, s in actual.get("tools", []))
        lines.append(f"| {r['case_id']} | {'yes' if r['hard_gate'] else ''} | {actual.get('outcome', '-')} | "
                     f"{tools} | {', '.join(actual.get('cited', []))} | {'yes' if r['passed'] else 'NO'} | "
                     f"{r.get('trace_id', '-')} |")
    failures = [r for r in report["cases"] if not r["passed"]]
    lines += ["", "## Failed checks", ""]
    lines += [f"- {r['case_id']}: " + "; ".join(f"{c['check']} ({c['detail']})" for c in r["checks"] if not c["passed"])
              for r in failures] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live evaluation suite against the API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="Bearer token of the employee under test")
    parser.add_argument("--other-token", help="Optional second employee, for cross-user access checks")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    report = run(args.base_url, args.token, args.other_token, args.output_dir)
    m = report["metrics"]
    print(f"{report['decision']}: pass {m['pass_rate']}, hard gates {m['hard_gates']}, "
          f"recall@3 {m['recall_at_3']}, citations {m['citation_validity']}, "
          f"p50/p95 {m['latency_p50_ms']}/{m['latency_p95_ms']} ms; gates {report['global_gates']}")
    print(f"Report: {args.output_dir / 'evaluation_report.json'} and evaluation_report.md")
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
