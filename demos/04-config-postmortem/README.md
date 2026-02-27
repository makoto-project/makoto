# Demo 04: The Config Postmortem

**Time:** 3 minutes | **Deps:** python3 (stdlib + sqlite3) | **Docker:** not needed

## The Story

Someone changes `max_batch_size` from 1000 to 50 at 3am. Monday morning, pipeline throughput has dropped 95%. Without an audit trail, the team spends hours digging through git blame and Slack history.

With DBOM audit entries on config changes, the who/what/when/why is answered in seconds.

## Run It

```bash
python3 demo.py
```

## What You'll See

1. **Part 1 (no DBOM):** Config changed, no record of who or why — hours of investigation
2. **Part 2 (with DBOM):** Same change, instant trace — signer, reason, old value, timestamp

## Key Files

| File | Purpose |
|------|---------|
| `demo.py` | The demo script (creates + cleans up temp SQLite DB) |

## What Else This Could Handle

- Config change approval workflows (require DBOM signature from two team members)
- Automatic rollback when config change correlates with alert
- Compliance reporting: "show all config changes in the last 90 days"
- Integration with feature flag systems (LaunchDarkly, Split)
