# Results

## Environment
- OS: Windows 11 (bash / msys2), x86-64
- Runtime/compiler: Python 3.14.3
- Dependency manager: pip (venv); runtime dependencies: none (stdlib only)
- Test framework: pytest 8.x

## Validation performed
- install: PASS (`pip install -e .` in a fresh venv)
- build: PASS (setuptools editable wheel; package has no build step beyond that)
- unit tests: PASS (57/57)
- integration tests: PASS (CLI end-to-end covered in `tests/test_planner.py::TestCli`)
- lint: N/A (no linter configured; stdlib-only, type-hinted)
- type check: N/A
- demo run: PASS (`init-demo` → `plan` → `show` → `validate` → `export-ics`)

## Commands executed
```shell
python -m venv .venv
.venv/bin/python.exe -m pip install -e .
.venv/bin/python.exe -m pip install pytest
.venv/bin/python.exe -m pytest -q
# 57 passed in 0.57s

.venv/bin/python.exe -m gapwright.cli init-demo
.venv/bin/python.exe -m gapwright.cli plan --calendar demo/calendar.ics \
  --tasks demo/tasks.json --out results/demo-plan.json --date 2026-10-01
.venv/bin/python.exe -m gapwright.cli show results/demo-plan.json
.venv/bin/python.exe -m gapwright.cli validate results/demo-plan.json
.venv/bin/python.exe -m gapwright.cli export-ics results/demo-plan.json \
  --out results/demo-plan.ics
```

## Observed result
Planning the demo day (standup 09:00–09:15, sprint planning 11:00–12:00,
code review 14:00–15:00) against 4 tasks produced this schedule:

```text
Plan for 2026-10-01
  09:15-10:15  Design sketch       p1  score=19.7143
  10:15-11:00  Review PRs          p3  score=16.0
  12:00-13:30  Write project spec  p2  score=14.6667
  13:30-14:00  Inbox zero          p5  score=12.0
OK: 4 block(s), no overlaps, times well-formed
```

The priority-1, deadline-driven task won the first big gap; the plan validator
confirmed no overlaps and well-formed times; the exported ICS re-parsed cleanly.

## Generated artifacts
- `results/demo-calendar.ics` — sample input calendar (3 meetings)
- `results/demo-tasks.json` — sample task list (4 tasks)
- `results/demo-plan.json` — generated plan (4 blocks)
- `results/demo-plan.ics` — plan exported back to iCalendar

## Known limitations
- Named TZIDs are handled as fixed UTC offsets registered at runtime; full
  DST-rule timezone databases are out of scope.
- RRULE supports DAILY/WEEKLY/MONTHLY with INTERVAL/COUNT/UNTIL/BYDAY/
  BYMONTHDAY; BYSETPOS/BYMONTH variants are not implemented.
- No network access of any kind; calendars must be exported to local .ics.
