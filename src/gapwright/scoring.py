"""Task scoring: best-fit slack, priority, urgency, deadline pressure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: int = 3        # 1 highest .. 5 lowest
    deadline: date | None = None

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError(f"task {self.title!r} duration must be positive")
        if not 1 <= self.priority <= 5:
            raise ValueError(f"task {self.title!r} priority must be 1..5")


def score_task(task: Task, gap_minutes: int, today: date) -> float:
    """Score how well a task fits a gap of gap_minutes (higher = better fit)."""
    if gap_minutes < task.duration_minutes:
        return float("-inf")

    slack = gap_minutes - task.duration_minutes
    fit = 1.0 / (1.0 + slack / 60.0)          # compact fits beat sprawling fits
    priority_bonus = (6 - task.priority) * 2.0

    urgency = 0.0
    if task.deadline:
        days_left = (task.deadline - today).days
        urgency = max(0.0, 5.0 - days_left)   # ramps up within 5 days

    return round(fit * 10.0 + priority_bonus + urgency, 4)
