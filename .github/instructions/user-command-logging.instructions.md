---
applyTo: '**'
---
For work in this repository, keep a plain-text, append-only record of each new user request in `logs/log.txt`. Add the entry before acting on the request, using one line per request in the format `YYYY-MM-DD: <request>`. Record only repository-related requests; do not backfill earlier conversation history.

Never write secrets, credentials, access tokens, or sensitive personal information to the log. Redact such content before recording it. If a request cannot be logged safely without retaining sensitive information, record a brief redacted summary instead. Do not overwrite or remove existing log entries.
