# gapwright architecture

## Overview

gapwright answers one question: *given the meetings I already have, when do my
tasks actually fit today?* It is a small, dependency-free pipeline:

```text
.ics file ──► ics.py ──► CalendarEvent[] ──► gaps.py ──► Gap[]
                                              │
tasks.json ───────────────────────────────────┼──► planner.py ──► Plan (JSON)
                                              │         │
                                              │         └──► export_ics() ──► .ics
                                              └── scoring.py feeds task×gap scores
                                                  into planner.py's best-fit loop
```

## Module walkthrough

### `ics.py` — calendar ingestion

- `_unfold` handles RFC 5545 line folding (continuation lines starting with a
  space/tab are joined to the previous logical line) and splits each line into
  `(NAME, params, value)`.
- `_parse_dt` accepts UTC (`Z`) datetimes, `VALUE=DATE` all-day forms, floating
  local times (treated as UTC), explicit UTC-offset values, and `TZID` names
  registered via `register_tz` (fixed-offset model; no DST database).
- `_parse_duration` implements the ISO-8601 subset used by iCalendar
  (`PnW`, `PnD`, `PnDTnHnMnS`, with optional sign).
- `_expand_rrule` supports `FREQ=DAILY/WEEKLY/MONTHLY` with `INTERVAL`,
  `COUNT`, `UNTIL`, `BYDAY` (weekday tokens), and `BYMONTHDAY`. Expansion is
  window-bounded so unbounded rules cannot loop forever (hard cap: 5000 steps).
- `EXDATE` occurrences are removed after expansion; per-event `TRANSP` and
  `STATUS` flags survive on every expanded occurrence.
- All-day events and multi-day events are marked non-busy (they block no
  work-day gaps by design).

### `gaps.py` — geometric core

- `merge_busy` sorts busy intervals and coalesces overlaps/adjacency, so
  back-to-back meetings leave no phantom 0-minute gaps.
- `free_gaps` intersects merged busy time with the configurable work window,
  optionally carves out a lunch window, then walks the day left-to-right
  emitting `Gap(start, end)` slices. `min_gap_minutes` filters slivers that no
  usable task would fit.

### `scoring.py` — fit quality

`score_task(task, gap_minutes, today)` returns `-inf` when the task cannot fit,
otherwise a weighted sum:

| Component | Formula | Rationale |
|---|---|---|
| fit | `1 / (1 + slack/60) * 10` | snug fills beat sprawling ones (less fragmentation) |
| priority | `(6 - priority) * 2` | P1 gains +10, P5 gains +2 |
| urgency | `max(0, 5 - days_to_deadline)` | deadlines within a week dominate |

### `planner.py` — the fitting loop and persistence

- `plan_day` runs a greedy global best-fit: repeatedly pick the highest-scoring
  (task, gap) pair across all remaining tasks and gaps, place it, shrink the
  gap, repeat. Deterministic given the same inputs.
- `TaskStore` implements optimistic locking: every write carries a
  `data_version`; `write_if_unchanged` refuses to clobber a store whose version
  moved (raises `ConflictError`). This makes concurrent edits safe without
  locks.
- `export_ics` renders a plan back to a RFC 5545 `VCALENDAR` so the plan is
  visible in any calendar client.

### `cli.py` — command surface

`init-demo`, `plan`, `show`, `validate`, `export-ics`, `store-check`,
`store-bump`. Exit codes: `0` success, `1` validation failure, `2` usage/IO
errors, `3` store conflict.

## Design decisions

- **Zero dependencies** — the entire ICS subset is hand-rolled (~300 lines);
  adding `icalendar`/`dateutil` would outscale the project's size.
- **UTC internally** — all datetimes are UTC; local zones enter only through
  explicit offsets at parse time.
- **Greedy over exact** — an exact assignment solver (bipartite matching) is
  overkill for ≤ dozens of tasks and harder to explain; greedy best-fit is
  transparent and deterministic.
