"""Tests for planner.py: plan_day, TaskStore, export_ics, and the CLI."""

import json
from datetime import datetime, time, timezone

import pytest

from gapwright.ics import CalendarEvent, parse_events
from gapwright.planner import (ConflictError, Plan, TaskStore, export_ics,
                               load_tasks, plan_day)

UTC = timezone.utc


def ev(h1, m1, h2, m2):
    return CalendarEvent(
        summary="busy",
        start=datetime(2026, 10, 1, h1, m1, tzinfo=UTC),
        end=datetime(2026, 10, 1, h2, m2, tzinfo=UTC),
    )


DAY = datetime(2026, 10, 1, tzinfo=UTC)


def make_task_store(tmp_path, tasks):
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps({"data_version": 1, "tasks": tasks}),
                 encoding="utf-8")
    return p


class TestPlanDay:
    def test_fills_gaps_in_order(self):
        events = [ev(9, 0, 9, 30), ev(12, 0, 13, 0)]
        from gapwright.scoring import Task
        tasks = [Task("A", 60), Task("B", 60)]
        plan = plan_day(events, tasks, DAY)
        assert len(plan.blocks) == 2
        assert plan.date == "2026-10-01"

    def test_no_double_booking(self):
        events = [ev(9, 0, 10, 0)]
        from gapwright.scoring import Task
        tasks = [Task("A", 90), Task("B", 90), Task("C", 90)]
        plan = plan_day(events, tasks, DAY, time(9), time(12))
        spans = []
        for b in plan.blocks:
            spans.append((b.start, b.end))
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            assert e1 <= s2, "blocks must not overlap"

    def test_unfit_task_omitted(self):
        events = [ev(9, 0, 9, 45)]
        from gapwright.scoring import Task
        tasks = [Task("huge", 240)]
        plan = plan_day(events, tasks, DAY, time(9), time(10))
        assert plan.blocks == []

    def test_blocks_within_work_window(self):
        from gapwright.scoring import Task
        tasks = [Task("A", 30)]
        plan = plan_day([], tasks, DAY, time(9), time(10))
        assert plan.blocks[0].start == "09:00"
        assert plan.blocks[0].end == "09:30"


class TestLoadTasks:
    def test_load_with_deadline(self, tmp_path):
        p = tmp_path / "t.json"
        p.write_text(json.dumps([
            {"title": "X", "duration_minutes": 30, "priority": 2,
             "deadline": "2026-10-05"},
            {"title": "Y", "duration_minutes": 45},
        ]), encoding="utf-8")
        tasks = load_tasks(p)
        assert tasks[0].deadline.isoformat() == "2026-10-05"
        assert tasks[1].priority == 3
        assert tasks[1].deadline is None


class TestTaskStore:
    def test_load_version(self, tmp_path):
        p = make_task_store(tmp_path, [{"title": "A", "duration_minutes": 30}])
        tasks, version = TaskStore(p).load()
        assert version == 1
        assert tasks[0].title == "A"

    def test_write_if_unchanged_success(self, tmp_path):
        p = make_task_store(tmp_path, [{"title": "A", "duration_minutes": 30}])
        store = TaskStore(p)
        tasks, version = store.load()
        from gapwright.scoring import Task
        tasks.append(Task("B", 45))
        store.write_if_unchanged(tasks, expected_version=version,
                                 new_version=version + 1)
        again, v2 = store.load()
        assert v2 == 2 and len(again) == 2

    def test_conflict_on_stale_version(self, tmp_path):
        p = make_task_store(tmp_path, [{"title": "A", "duration_minutes": 30}])
        store = TaskStore(p)
        _, version = store.load()
        # Simulate a concurrent writer.
        data = json.loads(p.read_text(encoding="utf-8"))
        data["data_version"] = 99
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ConflictError):
            store.write_if_unchanged([], expected_version=version,
                                     new_version=version + 1)


class TestExportIcs:
    def test_round_trip_structure(self):
        plan = Plan(date="2026-10-01")
        from gapwright.planner import PlanBlock
        plan.blocks = [PlanBlock("A", "09:00", "10:00", 2, 10.0)]
        ics = export_ics(plan)
        assert "BEGIN:VCALENDAR" in ics
        assert "SUMMARY:A" in ics
        assert "DTSTART:20261001T090000Z" in ics

    def test_exported_ics_parses(self):
        from gapwright.planner import PlanBlock
        plan = Plan(date="2026-10-01")
        plan.blocks = [PlanBlock("Deep work", "09:00", "10:30", 2, 10.0)]
        events = parse_events(export_ics(plan))
        assert len(events) == 1
        assert events[0].summary == "Deep work"


class TestCli:
    def test_plan_show_validate_export(self, tmp_path, capsys):
        from gapwright.cli import main
        cal = tmp_path / "cal.ics"
        cal.write_text(
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
            "UID:1\r\nDTSTART:20261001T120000Z\r\nDTEND:20261001T130000Z\r\n"
            "SUMMARY:Lunch meeting\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
            encoding="utf-8")
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps(
            [{"title": "Spec", "duration_minutes": 60, "priority": 1}]),
            encoding="utf-8")
        out = tmp_path / "plan.json"

        rc = main(["plan", "--calendar", str(cal), "--tasks", str(tasks),
                   "--out", str(out), "--date", "2026-10-01"])
        assert rc == 0
        plan_data = json.loads(out.read_text(encoding="utf-8"))
        assert plan_data["date"] == "2026-10-01"
        assert len(plan_data["blocks"]) == 1

        rc = main(["show", str(out)])
        assert rc == 0

        rc = main(["validate", str(out)])
        assert rc == 0

        ics_out = tmp_path / "plan.ics"
        rc = main(["export-ics", str(out), "--out", str(ics_out)])
        assert rc == 0
        assert "BEGIN:VCALENDAR" in ics_out.read_text(encoding="utf-8")

    def test_validate_rejects_overlap(self, tmp_path, capsys):
        from gapwright.cli import main
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({
            "date": "2026-10-01",
            "blocks": [
                {"task": "A", "start": "09:00", "end": "10:00",
                 "priority": 1, "score": 1.0},
                {"task": "B", "start": "09:30", "end": "10:30",
                 "priority": 1, "score": 1.0},
            ],
        }), encoding="utf-8")
        assert main(["validate", str(bad)]) == 1

    def test_conflict_exit_code(self, tmp_path, capsys):
        from gapwright.cli import main
        store = make_task_store(tmp_path, [{"title": "A",
                                            "duration_minutes": 30}])
        assert main(["store-check", str(store)]) == 0
        # Concurrent writer moves the version behind our back.
        data = json.loads(store.read_text(encoding="utf-8"))
        data["data_version"] = 42
        store.write_text(json.dumps(data), encoding="utf-8")
        # Stale expectation -> conflict exit code.
        assert main(["store-bump", str(store), "--expect-version", "1"]) == 3
        # Fresh expectation succeeds.
        assert main(["store-bump", str(store), "--expect-version", "42"]) == 0

    def test_bad_calendar_file(self, tmp_path, capsys):
        from gapwright.cli import main
        rc = main(["plan", "--calendar", str(tmp_path / "missing.ics"),
                   "--tasks", str(tmp_path / "t.json"),
                   "--out", str(tmp_path / "o.json")])
        assert rc == 2
