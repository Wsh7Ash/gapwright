"""Free-gap computation from busy calendar intervals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class Gap:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def merge_busy(events: list) -> list[tuple[datetime, datetime]]:
    """Merge overlapping/adjacent busy intervals from events."""
    busy = sorted((e.start, e.end) for e in events if e.busy)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def free_gaps(day: datetime, work_start: time, work_end: time,
              busy_events: list, min_gap_minutes: int = 0,
              lunch_start: time | None = None,
              lunch_end: time | None = None) -> list[Gap]:
    """Compute free gaps inside the work day, excluding busy and lunch windows."""
    day_floor = day.replace(hour=0, minute=0, second=0, microsecond=0)
    tz = day.tzinfo
    ws = datetime.combine(day_floor.date(), work_start, tzinfo=tz)
    we = datetime.combine(day_floor.date(), work_end, tzinfo=tz)
    if we <= ws:
        raise ValueError("work_end must be after work_start")

    # A lunch window inside the work day is treated as busy.
    busy: list[tuple[datetime, datetime]] = []
    if lunch_start and lunch_end and lunch_end > lunch_start:
        busy.append((datetime.combine(day_floor.date(), lunch_start, tzinfo=tz),
                     datetime.combine(day_floor.date(), lunch_end, tzinfo=tz)))

    for start, end in merge_busy(busy_events):
        # Intersect with work window only when it touches that day.
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)
        if end < ws or start > we:
            continue
        busy.append((max(start, ws), min(end, we)))

    busy.sort()
    merged: list[tuple[datetime, datetime]] = []
    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    gaps: list[Gap] = []
    cursor = ws
    for start, end in merged:
        if start > cursor:
            gaps.append(Gap(cursor, start))
        cursor = max(cursor, end)
    if cursor < we:
        gaps.append(Gap(cursor, we))

    min_td = timedelta(minutes=min_gap_minutes)
    return [g for g in gaps if g.minutes >= min_gap_minutes]
