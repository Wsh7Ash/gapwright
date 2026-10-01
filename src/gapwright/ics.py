"""ICS parsing: VCALENDAR/VEVENT unfolding, DTSTART/DTEND/DURATION, RRULE, EXDATE."""

from __future__ import annotations

import calendar as _cal
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

_ICAL_UTC = timezone.utc


class IcsParseError(ValueError):
    """Raised when calendar text cannot be parsed."""


@dataclass(frozen=True)
class CalendarEvent:
    summary: str
    start: datetime
    end: datetime
    uid: str = ""
    transparent: bool = False
    cancelled: bool = False

    @property
    def busy(self) -> bool:
        return not self.transparent and not self.cancelled


_TZ_OFFSETS: dict[str, timedelta] = {}


def register_tz(name: str, utc_offset_hours: float) -> None:
    """Register a named timezone as a fixed UTC offset (hours, may be fractional)."""
    _TZ_OFFSETS[name.strip().upper()] = timedelta(hours=utc_offset_hours)


register_tz("UTC", 0.0)
register_tz("GMT", 0.0)
register_tz("EET", 2.0)
register_tz("EEST", 3.0)


def _unfold(text: str) -> list[tuple[str, dict[str, str], str]]:
    """Unfold folded lines and split each into (name, params, value)."""
    logical: list[str] = []
    for raw in text.splitlines():
        if raw.startswith((" ", "\t")):
            if not logical:
                raise IcsParseError("continuation line before any content line")
            logical[-1] += raw[1:]
        else:
            logical.append(raw.rstrip("\r"))

    parsed: list[tuple[str, dict[str, str], str]] = []
    for line in logical:
        if not line.strip():
            continue
        if ":" not in line:
            raise IcsParseError(f"content line without ':' separator: {line!r}")
        head, value = line.split(":", 1)
        parts = head.split(";")
        name = parts[0].strip().upper()
        params: dict[str, str] = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.strip().upper()] = v.strip().strip('"')
        parsed.append((name, params, value))
    return parsed


_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def _parse_dt(value: str, params: dict[str, str]) -> datetime:
    """Parse DTSTART/DTEND values in date-time and all-day date forms."""
    value = value.strip()
    is_date = params.get("VALUE", "").upper() == "DATE" or bool(
        re.fullmatch(r"\d{8}", value))

    if "T" not in value and is_date:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=_ICAL_UTC)

    if "Z" in value:
        naive = value.rstrip("Zz")
        dt = datetime.strptime(naive, "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=_ICAL_UTC)

    tzid = params.get("TZID")
    if tzid and ("+" in value or value.count("-") >= 1 and "T" in value):
        m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})T(\d{2}):?(\d{2}):?(\d{2})"
                         r"([+-])(\d{2}):?(\d{2})?", value)
        if m:
            y, mo, d, hh, mm, ss, sign, oh, om = m.groups()
            offset = timedelta(hours=int(oh), minutes=int(om or 0))
            if sign == "-":
                offset = -offset
            dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss))
            return (dt - offset).replace(tzinfo=_ICAL_UTC)

    if tzid:
        key = tzid.upper()
        if key not in _TZ_OFFSETS:
            raise IcsParseError(f"unknown TZID {tzid!r}; register it with register_tz()")
        m = re.fullmatch(r"(\d{8})T(\d{6})", value)
        if not m:
            raise IcsParseError(f"invalid TZID datetime: {value!r}")
        local = datetime.strptime(m.group(1) + "T" + m.group(2), "%Y%m%dT%H%M%S")
        return (local - _TZ_OFFSETS[key]).replace(tzinfo=_ICAL_UTC)

    m = re.fullmatch(r"(\d{8})T(\d{6})", value)
    if m:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        return dt.replace(tzinfo=_ICAL_UTC)

    raise IcsParseError(f"unrecognized datetime value: {value!r}")


def _parse_duration(value: str) -> timedelta:
    """Parse an ISO-8601 iCalendar DURATION like P1DT2H30M, PT45M, P2W."""
    m = re.fullmatch(
        r"([+-]?)P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?",
        value.strip(),
    )
    if not m:
        raise IcsParseError(f"invalid DURATION: {value!r}")
    sign, w, d, h, mi, s = m.groups()
    td = timedelta(
        weeks=int(w or 0), days=int(d or 0), hours=int(h or 0),
        minutes=int(mi or 0), seconds=int(s or 0),
    )
    return -td if sign == "-" else td


def _expand_rrule(rule: str, dtstart: datetime, window_start: datetime,
                  window_end: datetime) -> list[datetime]:
    """Expand a bounded subset of RRULE into occurrences overlapping the window."""
    parts: dict[str, str] = {}
    for chunk in rule.split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.strip().upper()] = v.strip()

    freq = parts.get("FREQ", "").upper()
    if freq not in {"DAILY", "WEEKLY", "MONTHLY"}:
        raise IcsParseError(f"unsupported RRULE FREQ: {freq!r}")

    interval = max(1, int(parts.get("INTERVAL", "1")))
    count = int(parts["COUNT"]) if "COUNT" in parts else None
    until: datetime | None = None
    if "UNTIL" in parts:
        until = _parse_dt(parts["UNTIL"], {})

    byday: list[int] = []
    if "BYDAY" in parts:
        for token in parts["BYDAY"].split(","):
            token = token.strip().upper()
            if token in _WEEKDAYS:
                byday.append(_WEEKDAYS[token])
            else:
                raise IcsParseError(f"unsupported BYDAY token: {token!r}")

    bymonthday: list[int] = []
    if "BYMONTHDAY" in parts:
        bymonthday = [int(x) for x in parts["BYMONTHDAY"].split(",")]

    horizon = min(window_end, until) if until else window_end
    occurrences: list[datetime] = []
    t = dtstart
    max_iter = 5000

    def _emit(cand: datetime) -> bool:
        """Append cand if within window; return False when iteration must stop."""
        nonlocal occurrences
        end_of_cand = cand + (dtstart_end - dtstart)
        if end_of_cand < window_start or cand > horizon:
            if cand > horizon:
                return False
            return True
        occurrences.append(cand)
        return True

    dtstart_end = dtstart  # replaced below; duration handled by caller
    emitted = 0
    steps = 0
    while steps < max_iter:
        steps += 1
        candidate: datetime
        if freq == "DAILY":
            candidate = t
            t = t + timedelta(days=interval)
        elif freq == "WEEKLY":
            if byday:
                week_anchor = t - timedelta(days=t.weekday())
                week_occurrences: list[datetime] = []
                for wd in sorted(byday):
                    cand = week_anchor + timedelta(days=wd)
                    cand = cand.replace(hour=t.hour, minute=t.minute,
                                        second=t.second)
                    if cand < dtstart:
                        continue
                    week_occurrences.append(cand)
                if not week_occurrences:
                    t = week_anchor + timedelta(weeks=interval)
                    continue
                stop = False
                for cand in week_occurrences:
                    if count is not None and emitted >= count:
                        stop = True
                        break
                    if not _emit(cand):
                        stop = True
                        break
                    emitted += 1
                if stop:
                    break
                t = week_anchor + timedelta(weeks=interval)
                continue
            candidate = t
            t = t + timedelta(weeks=interval)
        else:  # MONTHLY
            if bymonthday:
                day = bymonthday[0]
                y, mo = t.year, t.month
                if day < 0:
                    last = _cal.monthrange(y, mo)[1]
                    day = last + 1 + day
                try:
                    candidate = t.replace(month=mo, day=day)
                except ValueError:
                    t = _add_months(t, interval)
                    continue
                t = _add_months(t, interval)
            else:
                candidate = t
                t = _add_months(t, interval)

        if count is not None and emitted >= count:
            break
        if not _emit(candidate):
            break
        emitted += 1

    return occurrences


def _add_months(t: datetime, n: int) -> datetime:
    total = (t.month - 1) + n
    y = t.year + total // 12
    mo = total % 12 + 1
    last = _cal.monthrange(y, mo)[1]
    return t.replace(year=y, month=mo, day=min(t.day, last))


def parse_events(text: str) -> list[CalendarEvent]:
    """Parse ICS text into CalendarEvent objects (RRULEs expanded).

    Recurring events are expanded only for the window spanned by all event
    start/end datetimes plus 366 days, which keeps expansion bounded.
    """
    tokens = _unfold(text)
    events: list[CalendarEvent] = []
    inside_event = False
    fields: dict[str, str] = {}
    params: dict[str, str] = {}
    rrule: str | None = None
    exdates: list[datetime] = []

    def _finish() -> None:
        nonlocal fields, params, rrule, exdates
        if "DTSTART" not in fields:
            fields, params, rrule, exdates = {}, {}, None, []
            return
        start = _parse_dt(fields["DTSTART"], params.get("DTSTART", {}))
        if "DTEND" in fields:
            end = _parse_dt(fields["DTEND"], params.get("DTEND", {}))
        elif "DURATION" in fields:
            end = start + _parse_duration(fields["DURATION"])
        else:
            end = start
        if end < start:
            raise IcsParseError(f"event {fields.get('UID', '?')!r} ends before it starts")

        all_day = start.tzinfo is _ICAL_UTC and start.time() == datetime.min.time() \
            and "T" not in fields["DTSTART"]
        if all_day or (end - start) > timedelta(days=1):
            events.append(CalendarEvent(
                summary=fields.get("SUMMARY", ""),
                start=start, end=end,
                uid=fields.get("UID", ""),
                transparent=True,
                cancelled=fields.get("STATUS", "").upper() == "CANCELLED",
            ))
            fields, params, rrule, exdates = {}, {}, None, []
            return

        transp = fields.get("TRANSP", "OPAQUE").upper() == "TRANSPARENT"
        cancelled = fields.get("STATUS", "").upper() == "CANCELLED"
        if rrule:
            window_start = min(e.start for e in events) if events else start
            window_end = max(e.end for e in events) if events else end
            window_end = max(window_end, start + timedelta(days=366))
            for occ in _expand_rrule(rrule, start, window_start, window_end):
                key = occ.strftime("%Y%m%dT%H%M%SZ")
                if any(ex.strftime("%Y%m%dT%H%M%SZ") == key for ex in exdates):
                    continue
                events.append(CalendarEvent(
                    summary=fields.get("SUMMARY", ""),
                    start=occ, end=occ + (end - start),
                    uid=fields.get("UID", ""),
                    transparent=transp,
                    cancelled=cancelled,
                ))
        else:
            if not any(ex == start for ex in exdates):
                events.append(CalendarEvent(
                    summary=fields.get("SUMMARY", ""),
                    start=start, end=end,
                    uid=fields.get("UID", ""),
                    transparent=transp,
                    cancelled=cancelled,
                ))
        fields, params, rrule, exdates = {}, {}, None, []

    for name, prms, value in tokens:
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            inside_event = True
            fields, params, rrule, exdates = {}, {}, None, []
            continue
        if name == "END" and value.strip().upper() == "VEVENT":
            if inside_event:
                _finish()
            inside_event = False
            continue
        if not inside_event:
            continue
        if name == "RRULE":
            rrule = value
        elif name == "EXDATE":
            for part in value.split(","):
                exdates.append(_parse_dt(part, prms))
        else:
            fields[name] = value
            params[name] = prms

    return events
