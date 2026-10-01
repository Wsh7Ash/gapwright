"""Task fitting, conflict-raising store, plan output, ICS export."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from .gaps import Gap, free_gaps
from .scoring import Task, score_task


class ConflictError(RuntimeError):
    """Raised when a concurrent write loses a data-version race."""


@dataclass
class PlanBlock:
    task: str
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    priority: int
    score: float


@dataclass
class Plan:
    date: str          # "YYYY-MM-DD"
    blocks: list[PlanBlock] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "date": self.date,
            "blocks": [asdict(b) for b in self.blocks],
        }, indent=2)


def load_tasks(path) -> list[Task]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tasks = []
    for raw in data:
        deadline = None
        if raw.get("deadline"):
            deadline = date.fromisoformat(raw["deadline"])
        tasks.append(Task(
            title=raw["title"],
            duration_minutes=int(raw["duration_minutes"]),
            priority=int(raw.get("priority", 3)),
            deadline=deadline,
        ))
    return tasks


def plan_day(events: list, tasks: list[Task], day: datetime,
             work_start: time = time(9, 0), work_end: time = time(17, 0),
             min_gap_minutes: int = 15,
             lunch_start: time | None = None,
             lunch_end: time | None = None) -> Plan:
    """Fit tasks into the day's free gaps using best-fit scoring."""
    gaps = free_gaps(day, work_start, work_end, events,
                     min_gap_minutes, lunch_start, lunch_end)
    today = day.date()
    remaining = sorted(tasks, key=lambda t: t.title)
    blocks: list[PlanBlock] = []

    # Repeatedly place the globally best (task, gap) pair.
    placed: list[tuple[Task, Gap]] = []
    unplaced = list(remaining)
    while unplaced:
        best = None  # (score, task, gap)
        for task in unplaced:
            for gap in gaps:
                s = score_task(task, gap.minutes, today)
                if s == float("-inf"):
                    continue
                if best is None or s > best[0]:
                    best = (s, task, gap)
        if best is None:
            break
        s, task, gap = best
        placed.append((task, gap))
        blocks.append(PlanBlock(
            task=task.title,
            start=gap.start.strftime("%H:%M"),
            end=(gap.start + timedelta(minutes=task.duration_minutes)).strftime("%H:%M"),
            priority=task.priority,
            score=s,
        ))
        # Shrink the gap by the placed duration.
        new_start = gap.start + timedelta(minutes=task.duration_minutes)
        gaps = [g for g in gaps if g is not gap]
        if new_start < gap.end:
            gaps.append(Gap(new_start, gap.end))
        gaps.sort(key=lambda g: g.start)
        unplaced.remove(task)

    return Plan(date=today.isoformat(), blocks=blocks)


class TaskStore:
    """JSON task store with optimistic locking via a data_version field."""

    def __init__(self, path):
        self.path = path

    def _read(self) -> dict:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def load(self) -> tuple[list[Task], int]:
        data = self._read()
        tasks = []
        for raw in data.get("tasks", []):
            deadline = None
            if raw.get("deadline"):
                deadline = date.fromisoformat(raw["deadline"])
            tasks.append(Task(
                title=raw["title"],
                duration_minutes=int(raw["duration_minutes"]),
                priority=int(raw.get("priority", 3)),
                deadline=deadline,
            ))
        return tasks, int(data.get("data_version", 0))

    def write_if_unchanged(self, tasks: list[Task], expected_version: int,
                           new_version: int) -> None:
        """Write tasks only if the stored data_version still equals expected."""
        current = self._read()
        if int(current.get("data_version", 0)) != expected_version:
            raise ConflictError(
                f"data_version moved: expected {expected_version}, "
                f"found {current.get('data_version')}")
        current["tasks"] = [
            {"title": t.title, "duration_minutes": t.duration_minutes,
             "priority": t.priority,
             "deadline": t.deadline.isoformat() if t.deadline else None}
            for t in tasks
        ]
        current["data_version"] = new_version
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)


def export_ics(plan: Plan) -> str:
    """Render a Plan back into VEVENT blocks in a VCALENDAR."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//gapwright//EN"]
    for i, b in enumerate(plan.blocks, 1):
        d = plan.date.replace("-", "")
        s = b.start.replace(":", "") + "00"
        e = b.end.replace(":", "") + "00"
        lines += [
            "BEGIN:VEVENT",
            f"UID:gapwright-{plan.date}-{i}@local",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{d}T{s}Z",
            f"DTEND:{d}T{e}Z",
            f"SUMMARY:{b.task}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
