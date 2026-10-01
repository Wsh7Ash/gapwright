"""Tests for gaps.py and scoring.py."""

from datetime import date, datetime, time, timezone

import pytest

from gapwright.gaps import Gap, free_gaps, merge_busy
from gapwright.ics import CalendarEvent
from gapwright.scoring import Task, score_task

UTC = timezone.utc


def ev(start_h, start_m, end_h, end_m, *, transparent=False, cancelled=False):
    return CalendarEvent(
        summary="x",
        start=datetime(2026, 10, 1, start_h, start_m, tzinfo=UTC),
        end=datetime(2026, 10, 1, end_h, end_m, tzinfo=UTC),
        transparent=transparent,
        cancelled=cancelled,
    )


class TestMergeBusy:
    def test_overlaps_merge(self):
        merged = merge_busy([ev(9, 0, 10, 0), ev(9, 30, 11, 0)])
        assert merged == [(datetime(2026, 10, 1, 9, tzinfo=UTC),
                           datetime(2026, 10, 1, 11, tzinfo=UTC))]

    def test_adjacent_merge(self):
        merged = merge_busy([ev(9, 0, 10, 0), ev(10, 0, 11, 0)])
        assert len(merged) == 1

    def test_disjoint_stay_separate(self):
        merged = merge_busy([ev(9, 0, 10, 0), ev(12, 0, 13, 0)])
        assert len(merged) == 2

    def test_transparent_and_cancelled_ignored(self):
        merged = merge_busy([ev(9, 0, 10, 0, transparent=True),
                             ev(11, 0, 12, 0, cancelled=True)])
        assert merged == []


class TestFreeGaps:
    DAY = datetime(2026, 10, 1, tzinfo=UTC)

    def test_empty_calendar_single_gap(self):
        gaps = free_gaps(self.DAY, time(9), time(17), [])
        assert len(gaps) == 1
        assert gaps[0].minutes == 480

    def test_meeting_splits_day(self):
        gaps = free_gaps(self.DAY, time(9), time(17), [ev(12, 0, 13, 0)])
        assert [g.minutes for g in gaps] == [180, 240]

    def test_min_gap_filters(self):
        gaps = free_gaps(self.DAY, time(9), time(17), [ev(9, 0, 16, 45)],
                         min_gap_minutes=30)
        assert gaps == []

    def test_lunch_excluded(self):
        gaps = free_gaps(self.DAY, time(9), time(17), [],
                         lunch_start=time(12, 30), lunch_end=time(13, 30))
        assert [g.minutes for g in gaps] == [210, 210]

    def test_out_of_window_meeting_ignored(self):
        gaps = free_gaps(self.DAY, time(9), time(17), [ev(7, 0, 8, 0)])
        assert gaps[0].minutes == 480

    def test_work_end_before_start_raises(self):
        with pytest.raises(ValueError):
            free_gaps(self.DAY, time(17), time(9), [])


class TestScoring:
    TODAY = date(2026, 10, 1)

    def test_task_too_big_for_gap(self):
        task = Task("big", 120)
        assert score_task(task, 60, self.TODAY) == float("-inf")

    def test_exact_fit_beats_slack(self):
        snug = Task("snug", 60, priority=3)
        loose = Task("loose", 30, priority=3)
        assert score_task(snug, 60, self.TODAY) > score_task(loose, 60, self.TODAY)

    def test_higher_priority_scores_higher(self):
        urgent = Task("urgent", 60, priority=1)
        chill = Task("chill", 60, priority=5)
        assert score_task(urgent, 120, self.TODAY) > score_task(chill, 120, self.TODAY)

    def test_deadline_urgency_ramps(self):
        soon = Task("soon", 60, deadline=date(2026, 10, 2))
        far = Task("far", 60, deadline=date(2026, 10, 28))
        assert score_task(soon, 120, self.TODAY) > score_task(far, 120, self.TODAY)

    def test_invalid_duration_raises(self):
        with pytest.raises(ValueError):
            Task("zero", 0)

    def test_invalid_priority_raises(self):
        with pytest.raises(ValueError):
            Task("bad", 30, priority=9)


class TestGap:
    def test_minutes(self):
        g = Gap(datetime(2026, 10, 1, 9, tzinfo=UTC),
                datetime(2026, 10, 1, 10, 30, tzinfo=UTC))
        assert g.minutes == 90
