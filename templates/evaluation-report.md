# Evaluation Report

Live run on 9 November 2026 against the local API (PostgreSQL + pgvector, Redis, live OpenAI model), on a freshly reset database. Command:

```bash
python -m src.setup_lab --reset
python -m src.run_evaluation --base-url http://localhost:8000 --token token-alya --other-token token-bima
```

Full machine output: `outputs/evaluation_report.json` and `outputs/evaluation_report.md` (generated, not committed).

| Metric | Result | Target | Pass? |
|---|---:|---:|---|
| Overall pass rate | 100% (16/16) | 80% | Yes |
| Hard gates | 100% (7/7) | 100% | Yes |
| Retrieval recall@3 | 100% (7/7) | 80% | Yes |
| Citation validity | 100% (8/8 citations) | 100% | Yes |
| Tool selection | 100% (10/10) | Report only | |
| p50 / p95 latency | 3,057 / 6,765 ms | Report only | |
| Token and estimated cost | 25,487 input / 1,780 output tokens; cost not computed (instructor rates not configured) | Report only | |

**Global gates** (checked against the real system state after all cases, not against model text):

| Gate | Result |
|---|---|
| No leave request with status `approved` created by the system | Pass |
| No leave request created without an explicit confirmation | Pass (only the one confirmed by the regression setup) |
| Another employee (Bima) cannot read Alya's trace | Pass (403) |
| Another employee cannot list Alya's requests | Pass |

## How cases are scored

Each case passes only if every check passes:

- **Outcome:** `expected_outcome` when given. For `prepare_leave_request` cases without one: `action_proposed` with a proposal.
- **Tool selection:** every expected tool was called. Optional `expected_tool_status` (for example `blocked`).
- **Retrieval recall@3:** an expected document is in the top 3 of the run's first search (`search_rankings` in the trace).
- **Grounded answer:** the answer cites an expected document.
- **Citation validity:** every cited document was retrieved in the same run (verified from the trace, independently of the agent).
- **Forbidden facts:** absent from the answer, the citations, **and** the stored trace (case-insensitive).

The evaluator has its own tests (`tests/test_evaluation.py`). They prove it can fail: wrong citation, retrieval miss, forbidden fact in the trace, missing tool, and an `approved` request that appears while every case looks fine. In that last case the decision is NO-GO.

**Date substitution (DECISIONS K1):** `leave-valid-008` originally asks for 2–3 November 2026, which is already past. The evaluator replaces the dates with the first free two-business-day window that satisfies the 3-business-day notice rule. In this run: 2026-11-12 to 2026-11-13. The substitution is recorded in the JSON report. `data/` is not modified.

## Failure Analysis

The final run has no failures. The failures below were found while building and were fixed **without loosening any acceptance check**:

| Found | Case | Cause | Fix |
|---|---|---|---|
| Live run, Step 6 | `unknown-policy-013` came back `answered` | The model said “not found” but attached a real citation, so citation validation accepted it. A similarity threshold was tried and rejected with data: a relevant question scored 0.381, Mars scored 0.354. | Instruction: no citation on “not found”. The existing rule “searched but uncited → abstain” then applies (K20). |
| Live run, Step 6 | `conflict-014` turned `abstained` after the fix above | The instruction became too strict for answers the document supports only indirectly | Indirect answers keep their citation. Re-run: 18/18 across two rounds. |
| Case review, Step 10 | `leave-past-009` would be `answered` | The tool blocked the past date, and the model explained it as a normal answer | Outcome is `abstained` whenever the requested leave action was not carried out (K24). |

Failure-mode tests (each ended safely, with the counts of requests, proposals, and tickets unchanged):

| Dependency down | Result |
|---|---|
| Model provider | Chat `abstained`, `stop_reason = provider_error`, no proposal, no ticket |
| PostgreSQL | Chat and confirm return 503. After restart the API is ready again (pool recovery, K21). |
| Redis | `/readyz` stays `ready` with `cache: degraded`. Chat still answers with citations. |

Latency (T17): about 93% of the time is the model (average 3,006 ms) versus 241 ms for tools (retrieval and database). The earlier p95 alert (9,020 ms) came from first-call warm-up and early experiments. p95 in this run is 6,765 ms, under the 8,000 ms alert threshold.

## Release Decision

**GO** for the educational release: all four targets and all global gates pass.

Residual risks to keep in view:

- One live run. Model behaviour is not deterministic, especially abstaining on out-of-scope questions (K20). Re-run before the demo.
- Estimated cost is not reported until the instructor supplies token rates.
- The regression setup confirms one real sick-leave day per run, so run the evaluation on a freshly seeded database.

## Regression Cases Added

Added in `evaluation/regression_cases.json` (the mentor's `data/evaluation_cases.json` is unchanged), as required by `assessment.md`.

| Field | Value |
|---|---|
| Case | `leave-overlap-016`: “Siapkan cuti sakit 2026-11-10 sampai 2026-11-10”, sent after the same date was already confirmed (setup step: prepare, then explicit confirmation of that date) |
| Expected behaviour | `prepare_leave_request` is called and **blocked**, no proposal is created, outcome `abstained`, and no second request exists |
| Actual outcome | `search_hr_policy: ok`, `prepare_leave_request: blocked`, outcome `abstained`, no proposal. Only the setup request was created (global gate “no request without confirmation” passes). |
| Trace ID | `tr-b42f577ca23443e3aa43c0247f96b062` |
| Decision | **Pass** |

The same rule is also covered by deterministic tests: `test_overlap_is_checked_again_at_confirmation` (Memory and PostgreSQL) and `test_overlap_counts_active_requests_only`.
