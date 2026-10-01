"""Tests for ics.py: datetime parsing, duration, RRULE, EXDATE."""

from datetime import datetime, timezone

import pytest

from gapwright.ics import IcsParseError, _parse_duration, _parse_dt, parse_events

UTC = timezone.utc


class TestParseDt:
    def test_utc_suffix(self):
        dt = _parse_dt("20261001T090000Z", {})
        assert dt == datetime(2026, 10, 1, 9, tzinfo=UTC)

    def test_all_day_date(self):
        dt = _parse_dt("20261001", {})
        assert dt == datetime(2026, 10, 1, tzinfo=UTC)

    def test_value_date_param(self):
        dt = _parse_dt("20261001", {"VALUE": "DATE"})
        assert dt == datetime(2026, 10, 1, tzinfo=UTC)

    def test_floating_treated_as_utc(self):
        dt = _parse_dt("20261001T093000", {})
        assert dt == datetime(2026, 10, 1, 9, 30, tzinfo=UTC)

    def test_registered_tz_offset(self):
        from gapwright import ics
        ics.register_tz("Asia/Amman", 3.0)
        dt = _parse_dt("20261001T120000", {"TZID": "Asia/Amman"})
        assert dt == datetime(2026, 10, 1, 9, tzinfo=UTC)  # 12:00+03:00

    def test_unknown_tz_raises(self):
        with pytest.raises(IcsParseError):
            _parse_dt("20261001T120000", {"TZID": "Mars/Olympus"})

    def test_garbage_raises(self):
        with pytest.raises(IcsParseError):
            _parse_dt("not-a-date", {})


class TestDuration:
    def test_minutes(self):
        assert _parse_duration("PT45M").total_seconds() == 2700

    def test_hours_minutes(self):
        assert _parse_duration("PT1H30M").total_seconds() == 5400

    def test_days(self):
        assert _parse_duration("P2D").days == 2

    def test_weeks(self):
        assert _parse_duration("P1W").days == 7

    def test_negative(self):
        assert _parse_duration("-PT30M").total_seconds() == -1800

    def test_invalid(self):
        with pytest.raises(IcsParseError):
            _parse_duration("PXX")


def _cal(*vevents: str) -> str:
    body = "".join(vevents)
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + body + "END:VCALENDAR\r\n")


class TestParseEvents:
    def test_simple_event(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20261001T090000Z\r\n"
            "DTEND:20261001T100000Z\r\nSUMMARY:Sync\r\nEND:VEVENT\r\n")
        events = parse_events(text)
        assert len(events) == 1
        assert events[0].summary == "Sync"
        assert events[0].start == datetime(2026, 10, 1, 9, tzinfo=UTC)
        assert events[0].busy

    def test_folded_line_unfolds(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20261001T090000Z\r\n"
            "DTEND:20261001T100000Z\r\nSUMMARY:Very long\r\n  summary here\r\n"
            "END:VEVENT\r\n")
        events = parse_events(text)
        assert events[0].summary == "Very long summary here"

    def test_duration_instead_of_dtend(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20261001T090000Z\r\n"
            "DURATION:PT30M\r\nSUMMARY:Brief\r\nEND:VEVENT\r\n")
        events = parse_events(text)
        assert events[0].end == datetime(2026, 10, 1, 9, 30, tzinfo=UTC)

    def test_transparent_not_busy(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20261001T090000Z\r\n"
            "DTEND:20261001T100000Z\r\nSUMMARY:Focus (shown as free)\r\n"
            "TRANSP:TRANSPARENT\r\nEND:VEVENT\r\n")
        assert not events_busy(parse_events(text))

    def test_cancelled_not_busy(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20261001T090000Z\r\n"
            "DTEND:20261001T100000Z\r\nSUMMARY:Off\r\nSTATUS:CANCELLED\r\n"
            "END:VEVENT\r\n")
        assert not events_busy(parse_events(text))

    def test_all_day_events_skipped(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART;VALUE=DATE:20261001\r\n"
            "DTEND;VALUE=DATE:20261002\r\nSUMMARY:Conference\r\nEND:VEVENT\r\n")
        events = parse_events(text)
        assert len(events) == 1
        assert not events_busy(events)

    def test_daily_rrule_expands(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:r\r\nDTSTART:20261001T100000Z\r\n"
            "DTEND:20261001T103000Z\r\nSUMMARY:Pill\r\n"
            "RRULE:FREQ=DAILY;COUNT=5\r\nEND:VEVENT\r\n")
        events = parse_events(text)
        assert len(events) == 5
        assert events[3].start == datetime(2026, 10, 4, 10, tzinfo=UTC)

    def test_weekly_rrule_byday(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:r\r\nDTSTART:20261001T090000Z\r\n"  # Thu
            "DTEND:20261001T093000Z\r\nSUMMARY:Standup\r\n"
            "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=6\r\nEND:VEVENT\r\n")
        events = parse_events(text)
        assert len(events) == 6
        # Weekdays of occurrences must be Mon/Wed/Fri only.
        assert all(e.start.weekday() in (0, 2, 4) for e in events)

    def test_exdate_removes_occurrence(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:r\r\nDTSTART:20261001T100000Z\r\n"
            "DTEND:20261001T103000Z\r\nSUMMARY:Class\r\n"
            "RRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20261002T100000Z\r\n"
            "END:VEVENT\r\n")
        events = parse_events(text)
        assert len(events) == 2
        starts = {e.start.day for e in events}
        assert 2 not in starts

    def test_interval_two_weeks(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:r\r\nDTSTART:20261001T090000Z\r\n"
            "DTEND:20261001T093000Z\r\nSUMMARY:Biweekly\r\n"
            "RRULE:FREQ=WEEKLY;INTERVAL=2;COUNT=3\r\nEND:VEVENT\r\n")
        events = parse_events(text)
        assert len(events) == 3
        assert (events[1].start - events[0].start).days == 14

    def test_unsupported_freq_raises(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:r\r\nDTSTART:20261001T090000Z\r\n"
            "DTEND:20261001T093000Z\r\nSUMMARY:Yearly\r\n"
            "RRULE:FREQ=YEARLY;COUNT=2\r\nEND:VEVENT\r\n")
        with pytest.raises(IcsParseError):
            parse_events(text)

    def test_end_before_start_raises(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20261001T100000Z\r\n"
            "DTEND:20261001T090000Z\r\nSUMMARY:Backwards\r\nEND:VEVENT\r\n")
        with pytest.raises(IcsParseError):
            parse_events(text)

    def test_no_dtstart_skips_event(self):
        text = _cal(
            "BEGIN:VEVENT\r\nUID:1\r\nSUMMARY:No time\r\nEND:VEVENT\r\n")
        assert parse_events(text) == []


def events_busy(events) -> bool:
    return any(e.busy for e in events)
