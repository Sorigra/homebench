# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - Exercise list-driven flows with more than one item, so an implementation that only handles the first element cannot pass.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `cli` · harmful: 0
- features: model-lifecycle
- evidence: validation.md sensor M16 (src/homebench/cli.py:326) (cli)
- last seen: 2026-08-28T05:53:27Z

### L-002 - A test that is skipped by default is zero evidence; never mark a requirement covered by it.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `tests` · harmful: 0
- features: model-lifecycle
- evidence: MLC-15 - tests/test_live_router.py:24-27 (skipped) (tests)
- last seen: 2026-08-28T05:53:27Z

### L-003 - Give every listed edge case its own task and test, or move it to Out of Scope explicitly.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `specs` · harmful: 0
- features: model-lifecycle
- evidence: spec.md Edge Cases: models-max retry, in-flight request warning (specs)
- last seen: 2026-08-28T05:53:27Z

### L-004 - Assert inherited behaviour a new feature depends on; pre-existing code with no test counts as uncovered.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `tests` · harmful: 0
- features: model-lifecycle
- evidence: MLC-11 - src/homebench/runner.py:182-184 (tests)
- last seen: 2026-08-28T05:53:27Z

### L-005 - State where a recorded failure must surface; otherwise 'record the failure' is satisfied by a field nothing reads.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `specs` · harmful: 0
- features: model-lifecycle
- evidence: MLC-14 AC2 - src/homebench/providers/llamacpp.py:63 (specs)
- last seen: 2026-08-28T05:53:27Z

### L-006 - Wire every branch of a resolution chain to a real caller; a tier reachable only from tests is dead code.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `cli` · harmful: 0
- features: model-lifecycle
- evidence: P2 AC5 heuristic tier - src/homebench/cli.py:328 (cli)
- last seen: 2026-08-28T05:53:27Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
