# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-01

### Added
- ICS parser: UTC/date/floating/TZID-offset datetimes, DURATION, line unfolding.
- RRULE expansion for DAILY/WEEKLY/MONTHLY with INTERVAL, COUNT, UNTIL, BYDAY,
  BYMONTHDAY; EXDATE exclusion; per-event TRANSP/STATUS handling.
- Free-gap computation with busy merge, lunch carving, minimum-gap filtering.
- Best-fit task scoring (compactness, priority, deadline urgency) with a
  deterministic greedy placement loop.
- Plan JSON output, validation (overlap/format), and ICS re-export.
- Task store with optimistic locking (`data_version`) and ConflictError.
- CLI: `init-demo`, `plan`, `show`, `validate`, `export-ics`, `store-check`,
  `store-bump`.
- Full pytest suite covering parser, gaps, scoring, planner, store, and CLI.
