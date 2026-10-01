# gapwright

**gapwright** builds a realistic focus-block day plan by fitting your tasks into the free
gaps between existing calendar meetings, then exports the result as `.ics` events your
calendar app can display.

## The problem

Traditional to-do apps assume your day is empty. In reality your calendar is full, and
the question "when do I actually do this work?" is answered by hunting for gaps between
meetings, guessing travel/buffer needs, and hoping you do not overbook yourself. gapwright
automates that hunt: it reads the calendar you already have, measures the gaps, and
places tasks into the gaps that genuinely fit.

## Key features

- **ICS parsing** — reads standard `VCALENDAR`/`VEVENT` files; `DTSTART`/`DTEND`,
  `VALUE=DATE-TIME` and `VALUE=DATE` forms, UTC `Z` suffixes, `TZID` parameters (UTC-offset
  math), `DURATION` (ISO-8601 `PnDTnHnMnS`), `RRULE` with `FREQ=DAILY/WEEKLY/MONTHLY`
  plus `INTERVAL`, `COUNT`, `UNTIL`, `BYDAY`, and `EXDATE`, per-event
  `TRANSP:TRANSPARENT` and per-event `STATUS:CANCELLED`, and line unfolding.
- **Free-gap finder** — busy intervals are merged and complemented against the work day,
  so overlapping meetings and recurring series behave correctly.
- **Gap scoring** — best-fit scoring considers leftover slack (fragmentation penalty),
  priority and urgency of the task, and deadline proximity; the best tasks win the best
  gaps.
- **Work-day configuration** — start, end, lunch window, and minimum gap residual are all
  configurable.
- **Optimistic locking** — concurrent writers use atomic `create`/`write_if_unchanged`
  with a data-version check; a stale writer gets `ConflictError` instead of clobbering.
- **Deterministic output** — a fixed RNG seed yields stable scores, so the same inputs
  always produce the same plan.
- **ICS export** — the planned blocks round-trip back out as `VEVENT` blocks.
- **CLI + library** — use it as a script or import `gapwright.planner` from Python.

## Architecture summary

```text
src/gapwright/
├─ ics.py        # ICS lexer/parser → CalendarEvent (incl. RRULE expansion, EXDATE)
├─ gaps.py       # busy-interval merge + free-gap computation
├─ scoring.py    # task scoring: slack, priority, urgency, deadline pressure
├─ planner.py    # task fitting, conflict-raising store, plan output
└─ cli.py        # argparse entry point (plan/validate)
tests/           # pytest unit tests (parser, gaps, scoring, planner, CLI)
```

## Requirements

- Python 3.12+ (no third-party dependencies)

## Installation

```shell
pip install -e .
```

## Quick start

```shell
# Generate a sample calendar + task list in ./demo
python -m gapwright.cli init-demo

# Plan tasks into the calendar gaps
python -m gapwright.cli plan --calendar demo/calendar.ics --tasks demo/tasks.json --out plan.json

# Show the plan as human-readable table + validate it
python -m gapwright.cli show plan.json
python -m gapwright.cli validate plan.json

# Export the plan back to ICS
python -m gapwright.cli export-ics plan.json --out plan.ics
```

Example plan JSON:

```json
{
  "date": "2026-10-01",
  "blocks": [
    {
      "task": "Write project spec",
      "start": "09:30",
      "end": "11:00",
      "priority": 3,
      "score": 12.4
    }
  ]
}
```

## Configuration

CLI flags on `plan`:

| Flag | Default | Meaning |
|---|---|---|
| `--calendar PATH` | required | input `.ics` file |
| `--tasks PATH` | required | tasks JSON file |
| `--out PATH` | required | plan output JSON |
| `--work-start HH:MM` | `09:00` | work day start |
| `--work-end HH:MM` | `17:00` | work day end |
| `--min-gap-minutes N` | `15` | minimum residual gap to use |
| `--seed N` | `42` | RNG seed (deterministic scoring) |

Tasks file format:

```json
[
  {"title": "Write spec", "duration_minutes": 90, "priority": 3, "deadline": "2026-10-03"}
]
```

- `priority`: 1 (highest) .. 5 (lowest)
- `deadline` (optional): `YYYY-MM-DD`; earlier deadlines raise urgency

## Testing

```shell
pip install pytest
pytest -v
```

## Project structure

See "Architecture summary" above; `docs/ARCHITECTURE.md` has the module-by-module
walkthrough and `docs/USAGE.md` has task/schema details.

## Limitations

- UTC-offset `TZID` handling treats named zones via their UTC offset for the event's
  start/end; full DST-rule timezone databases are intentionally out of scope.
- No remote calendar fetching — feed it an `.ics` file you export or sync locally.
- Recurrence expansion is bounded (no `BYSETPOS`/`BYMONTHDAY` variants yet).

## Roadmap

- `BYSETPOS` and `BYMONTHDAY` RRULE support
- Optional travel-time buffers between non-adjacent blocks
- `--ical-busy` flag to emit busy-check .ics instead of planned blocks

## Security notes

gapwright processes local files only and performs no network I/O. It never sends your
calendar or task contents anywhere. Do not point it at calendars you are not authorized
to read.

## License

MIT
