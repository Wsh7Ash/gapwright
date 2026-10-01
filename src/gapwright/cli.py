"""gapwright CLI: plan tasks into calendar gaps, show, validate, export."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time

from .ics import IcsParseError, parse_events
from .planner import (ConflictError, Plan, PlanBlock, TaskStore, export_ics,
                      load_tasks, plan_day)

DEMO_CALENDAR = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//gapwright demo//EN
BEGIN:VEVENT
UID:standup@gapwright
DTSTART:20261001T090000Z
DTEND:20261001T091500Z
SUMMARY:Daily standup
END:VEVENT
BEGIN:VEVENT
UID:planning@gapwright
DTSTART:20261001T110000Z
DTEND:20261001T120000Z
SUMMARY:Sprint planning
END:VEVENT
BEGIN:VEVENT
UID:review@gapwright
DTSTART:20261001T140000Z
DTEND:20261001T150000Z
SUMMARY:Code review
END:VEVENT
END:VCALENDAR
"""

DEMO_TASKS = [
    {"title": "Write project spec", "duration_minutes": 90, "priority": 2},
    {"title": "Review PRs", "duration_minutes": 45, "priority": 3},
    {"title": "Inbox zero", "duration_minutes": 30, "priority": 5},
    {"title": "Design sketch", "duration_minutes": 60, "priority": 1,
     "deadline": "2026-10-02"},
]


def cmd_init_demo(args) -> int:
    import os
    os.makedirs("demo", exist_ok=True)
    with open("demo/calendar.ics", "w", encoding="utf-8", newline="") as f:
        f.write(DEMO_CALENDAR)
    with open("demo/tasks.json", "w", encoding="utf-8") as f:
        json.dump(DEMO_TASKS, f, indent=2)
    print("Wrote demo/calendar.ics and demo/tasks.json")
    return 0


def cmd_plan(args) -> int:
    try:
        with open(args.calendar, encoding="utf-8") as f:
            events = parse_events(f.read())
    except (OSError, IcsParseError) as exc:
        print(f"error: cannot read calendar: {exc}", file=sys.stderr)
        return 2
    try:
        tasks = load_tasks(args.tasks)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: cannot read tasks: {exc}", file=sys.stderr)
        return 2

    day = datetime.fromisoformat(args.date) if args.date else datetime.now()
    if day.tzinfo is None:
        day = day.astimezone()
    work_start = time.fromisoformat(args.work_start)
    work_end = time.fromisoformat(args.work_end)
    if work_end <= work_start:
        print("error: work-end must be after work-start", file=sys.stderr)
        return 2

    plan = plan_day(events, tasks, day, work_start, work_end,
                    args.min_gap_minutes)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(plan.to_json())
    print(f"Planned {len(plan.blocks)} block(s) -> {args.out}")
    return 0


def cmd_show(args) -> int:
    try:
        with open(args.plan, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read plan: {exc}", file=sys.stderr)
        return 2
    plan = Plan(date=data["date"],
                blocks=[b for b in data.get("blocks", [])])
    if not plan.blocks:
        print(f"Plan for {plan.date}: (no blocks)")
        return 0
    width = max(len(b["task"]) for b in plan.blocks)
    print(f"Plan for {plan.date}")
    for b in plan.blocks:
        print(f"  {b['start']}-{b['end']}  {b['task']:<{width}}  "
              f"p{b['priority']}  score={b['score']}")
    return 0


def cmd_validate(args) -> int:
    try:
        with open(args.plan, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read plan: {exc}", file=sys.stderr)
        return 2
    errors: list[str] = []
    blocks = data.get("blocks", [])
    for i, b in enumerate(blocks):
        if not b.get("task"):
            errors.append(f"block {i}: missing task")
        for key in ("start", "end"):
            try:
                time.fromisoformat(b.get(key, ""))
            except (TypeError, ValueError):
                errors.append(f"block {i}: bad {key}")
    for a, b in zip(blocks, blocks[1:]):
        if b["start"] < a["end"]:
            errors.append(f"overlap: {a['task']!r} and {b['task']!r}")
    if errors:
        for e in errors:
            print(f"INVALID: {e}", file=sys.stderr)
        return 1
    print(f"OK: {len(blocks)} block(s), no overlaps, times well-formed")
    return 0


def cmd_export_ics(args) -> int:
    try:
        with open(args.plan, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read plan: {exc}", file=sys.stderr)
        return 2
    plan = Plan(
        date=data["date"],
        blocks=[PlanBlock(**b) for b in data.get("blocks", [])],
    )
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(export_ics(plan))
    print(f"Wrote {args.out}")
    return 0


def cmd_store_check(args) -> int:
    store = TaskStore(args.store)
    try:
        tasks, version = store.load()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"version={version} tasks={len(tasks)}")
    return 0


def cmd_store_bump(args) -> int:
    store = TaskStore(args.store)
    try:
        tasks, version = store.load()
        expected = args.expect_version if args.expect_version is not None else version
        store.write_if_unchanged(tasks, expected_version=expected,
                                 new_version=version + 1)
    except ConflictError as exc:
        print(f"CONFLICT: {exc}", file=sys.stderr)
        return 3
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"bumped to version {version + 1}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gapwright",
                                description="Plan tasks into calendar gaps")
    sub = p.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("init-demo", help="write sample calendar+tasks")
    demo.set_defaults(func=cmd_init_demo)

    plan = sub.add_parser("plan", help="fit tasks into calendar gaps")
    plan.add_argument("--calendar", required=True)
    plan.add_argument("--tasks", required=True)
    plan.add_argument("--out", required=True)
    plan.add_argument("--date", help="YYYY-MM-DD (default: today)")
    plan.add_argument("--work-start", default="09:00")
    plan.add_argument("--work-end", default="17:00")
    plan.add_argument("--min-gap-minutes", type=int, default=15)
    plan.set_defaults(func=cmd_plan)

    show = sub.add_parser("show", help="print a plan as a table")
    show.add_argument("plan")
    show.set_defaults(func=cmd_show)

    val = sub.add_parser("validate", help="check a plan for overlap/format")
    val.add_argument("plan")
    val.set_defaults(func=cmd_validate)

    ex = sub.add_parser("export-ics", help="export a plan as .ics")
    ex.add_argument("plan")
    ex.add_argument("--out", required=True)
    ex.set_defaults(func=cmd_export_ics)

    sc = sub.add_parser("store-check", help="show task store version+count")
    sc.add_argument("store")
    sc.set_defaults(func=cmd_store_check)

    sb = sub.add_parser("store-bump", help="bump store version (optimistic lock demo)")
    sb.add_argument("store")
    sb.add_argument("--expect-version", type=int, default=None,
                    help="fail with exit 3 unless stored data_version equals this")
    sb.set_defaults(func=cmd_store_bump)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
