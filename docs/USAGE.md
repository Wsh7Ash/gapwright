# gapwright usage guide

## Typical workflow

```shell
# 1. Export a day (or week) from your calendar app as .ics
#    (Google Calendar → Settings → Export; Outlook → Save As .ics)

# 2. Describe your tasks
cat > tasks.json <<'EOF'
[
  {"title": "Write Q4 report", "duration_minutes": 120, "priority": 2},
  {"title": "Review PR #41",   "duration_minutes": 45,  "priority": 1, "deadline": "2026-10-02"},
  {"title": "Triage inbox",    "duration_minutes": 30,  "priority": 5}
]
EOF

# 3. Plan
gapwright plan --calendar day.ics --tasks tasks.json --out plan.json

# 4. Inspect, validate, export back to your calendar
gapwright show plan.json
gapwright validate plan.json
gapwright export-ics plan.json --out focus-blocks.ics
```

## Task schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | shown in plan and exported event summary |
| `duration_minutes` | int | yes | must be > 0 |
| `priority` | 1..5 | no (default 3) | 1 = most important |
| `deadline` | `YYYY-MM-DD` | no | urgency rises within 5 days |

## Task store (optional)

For tools that edit the task list concurrently, wrap it in a store document:

```json
{
  "data_version": 7,
  "tasks": [ {"title": "...", "duration_minutes": 30} ]
}
```

```shell
gapwright store-check tasks-store.json   # prints version + count
gapwright store-bump tasks-store.json    # refuses on stale version (exit 3)
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | plan validation failed (overlap or malformed times) |
| 2 | unreadable/malformed input files |
| 3 | optimistic-lock conflict |

## Tips

- Set `--min-gap-minutes 30` to stop sliver gaps from being fragmented further.
- Model lunch with `--work-start 09:00 --work-end 17:00` plus a busy
  `TRANSP:OPAQUE` lunch event, or split the work window manually.
- Mark informal "optional" holds as `TRANSP:TRANSPARENT` in your calendar;
  gapwright will treat that time as free.
