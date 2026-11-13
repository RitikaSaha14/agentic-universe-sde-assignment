# Assignment A — Interaction Ledger & Reporting Pipeline

Python 3.11+ implementation using SQLite. The CLI is `pipeline.py`.

## Setup

From the repository root:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Set a stable encryption secret before ingesting data. Keep it private and use the same value for every run against the same database.

```powershell
# Windows PowerShell (current terminal only)
$env:LEDGER_ENCRYPTION_KEY = "replace-with-a-long-random-secret"
```

```bash
# macOS/Linux
export LEDGER_ENCRYPTION_KEY="replace-with-a-long-random-secret"
```

For local experimentation only, the program has a documented development fallback. Do not use that fallback for real data.

## Generate and ingest

```bash
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data
python solution/pipeline.py --db data/ledger.sqlite ingest data/drop_1
python solution/pipeline.py --db data/ledger.sqlite ingest data/drop_2
python solution/pipeline.py --db data/ledger.sqlite report --out reports
```

To run against a different seed, generate into a new directory and use a new database. Ingesting the same drop again is a no-op.

## Tests

```bash
python -m pytest solution/tests -q
```

## Design summary

- SQLite stores leads, encrypted event payloads, processed-file fingerprints, counters, and rejections.
- Canonical phone values are encrypted with Fernet. A keyed HMAC-SHA256 digest supports deterministic matching without storing plaintext phone numbers.
- Customer names are encrypted. Non-PII lead attributes are stored as JSON.
- Events are immutable rows keyed by globally unique `event_id`. Duplicate IDs are dropped.
- Event-to-lead resolution is recalculated when reports are generated. This lets an event that was previously orphaned become linkable after a later lead batch arrives.
- Only `disposition.override` uses `call_id` for linking; other event types require a matching valid phone.
- Reports are generated from the stored ledger and current lead set.

The encryption secret must remain stable for the lifetime of a database. Rotating it requires a planned re-encryption migration.
