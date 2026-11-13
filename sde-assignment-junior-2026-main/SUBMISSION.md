# Submission

> Replace everything in _italics_. Be concise: bullet points are fine. We read every word.

## Candidate
- **Name:** Ritika Saha
- **Assignment chosen:** A (Data)
- **Time spent (honest estimate):** 7h

## How to run
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:LEDGER_ENCRYPTION_KEY = "your-long-random-secret"

python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data

python solution/pipeline.py --db data/ledger.sqlite ingest data/drop_1
python solution/pipeline.py --db data/ledger.sqlite ingest data/drop_2

python solution/pipeline.py --db data/ledger.sqlite report --out reports

python -m pytest solution/tests -q
```

## Design
The implementation uses Python 3.11+ with SQLite as the persistent storage layer.

- Leads are ingested from CSV files and stored with encrypted customer information.
- Phone numbers are encrypted using Fernet. A keyed HMAC-SHA256 digest enables deterministic matching without storing plaintext phone numbers.
- Customer names are encrypted, while non-PII lead attributes are stored as JSON.
- Call events are stored as immutable records keyed by globally unique event IDs. Duplicate event IDs are ignored.
- Event-to-lead relationships are resolved during report generation. This allows previously orphaned events to become linkable when matching leads arrive later.
- Only `disposition.override` events use `call_id` for linking; other event types require a matching valid phone number.
- Reports are generated from the stored interaction ledger and current lead data.

The encryption key must remain stable for the lifetime of a database. Key rotation would require a planned re-encryption migration.

## Decisions & assumptions
_Every place where you made a call the spec didn't make for you, and why._

| Decision | Why | Alternative considered |
|---|---|---|
| _ | _ | _ |

## Failure modes considered
_What can go wrong and how your solution handles it (bad input, re-runs, crashes, timeouts,
duplicates...). Also list anything you know is **not** handled._

## Testing
_What you tested, what you didn't, and why._

## Results
_For A: timings, and anything surprising in the data. For B: your `/admin/report` summary from
a full run, ideally one that includes a `kill -9`._

## If I had another day
_What you'd do next, in priority order._
