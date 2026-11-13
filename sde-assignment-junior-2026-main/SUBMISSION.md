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
| SQLite for persistence | Simple local setup and sufficient for the assignment's scale | PostgreSQL |
| Fernet encryption for phone numbers and customer names | Protects personally identifiable information at rest | Plaintext storage |
| Keyed HMAC-SHA256 for phone matching | Enables deterministic matching without storing plaintext phone numbers | Hashing without a secret |
| Immutable event records keyed by event ID | Prevents duplicate event processing and preserves the original event history | Updating existing event records |
| Resolve event-to-lead relationships during reporting | Allows previously orphaned events to become linked when leads arrive later | Permanently storing unresolved relationships |
| Day-first date parsing | Follows the assignment's expected input convention | Locale-dependent date parsing |

## Failure modes considered
- Invalid phone numbers are rejected during normalization.
- Invalid or impossible dates are rejected.
- Duplicate event IDs are ignored.
- Re-ingesting an already processed lead file does not increase lead counts.
- Orphan events are retained and can become linkable when a matching lead is ingested later.
- Disposition overrides take precedence over normal disposition events.
- The encryption key must remain stable across runs against the same database.

Known limitations:
- Encryption key rotation requires a planned re-encryption migration.
- SQLite is intended for this assignment's local workload rather than high-concurrency production use.
- Production-scale monitoring, automated recovery and distributed processing are outside the current implementation.

## Testing
Automated tests are included for:

- Indian phone number normalization and invalid number rejection.
- Day-first date parsing and impossible date validation.
- Decimal parsing and currency formatting.
- Disposition override precedence.
- Latest disposition selection when no override exists.
- Lead bucket priority and classification.
- Orphan event recovery after a matching lead is ingested.
- Lead re-ingestion idempotency and counter consistency.

Run tests using:

python -m pytest solution/tests -q
## Results
- Successfully implemented the Assignment A ingestion and reporting pipeline using Python and SQLite.
- Added automated tests covering core normalization, classification, disposition and idempotency behavior.
- Verified that an initially orphaned event becomes linked after the corresponding lead is ingested.
- Verified that re-ingesting the same lead file does not increase the lead count.

Report outputs:
- batch_summary.csv
- daily_overview.csv
- lead_report.csv
- rejections.csv
- data_quality.json

## If I had another day
1. Add more integration tests using larger and dirtier synthetic datasets.
2. Improve structured logging and error diagnostics for failed ingestion batches.
3. Add a documented encryption key rotation and recovery process.
4. Benchmark ingestion and reporting performance with larger datasets.
5. Improve database indexing and query performance where needed.
