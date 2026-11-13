from datetime import datetime
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pipeline


def test_phone_normalization():
    assert pipeline.phone_normalize("91-77187-50036") == "+917718750036"
    assert pipeline.phone_normalize("(+91) 77187 50036") == "+917718750036"
    assert pipeline.phone_normalize("07718750036") == "+917718750036"
    assert pipeline.phone_normalize("022-2222-3333") is None
    assert pipeline.phone_normalize("5712345678") is None


def test_dates_are_day_first_and_validated():
    assert pipeline.parse_date("01-Dec-2026") == "2026-12-01"
    assert pipeline.parse_date("03/10/2026") == "2026-10-03"
    try:
        pipeline.parse_date("31/02/2026")
    except ValueError:
        pass
    else:
        assert False, "impossible date accepted"


def test_effective_disposition_override_wins_even_if_older_than_set():
    facts = [
        ("disposition.set", datetime(2026, 10, 1), "renewed"),
        ("disposition.override", datetime(2026, 10, 2), "not_interested"),
    ]
    assert pipeline.effective_disposition(facts) == "not_interested"


def test_latest_set_used_without_override():
    facts = [
        ("disposition.set", datetime(2026, 10, 1), "callback_requested"),
        ("disposition.set", datetime(2026, 10, 2), "renewed"),
    ]
    assert pipeline.effective_disposition(facts) == "renewed"


def test_bucket_priority():
    catalogue = {"renewed": {"terminal": True}}
    assert pipeline.lead_bucket({}, {}, catalogue) == "yet_to_reach_out"
    calls = {"a": {"call.telephony_failed": True}, "b": {"call.telephony_failed": True}}
    assert pipeline.lead_bucket(calls, {}, catalogue) == "in_progress_telephony_failed"
    assert pipeline.lead_bucket(calls, {"a": "renewed"}, catalogue) == "completed"
    assert pipeline.lead_bucket({"a": {}}, {}, catalogue) == "in_progress_dialed"


def test_decimal_formats():
    assert pipeline.parse_decimal("₹12,345") == "12345.00"
    assert pipeline.parse_decimal("Rs. 120.456") == "120.46"


def test_orphan_event_becomes_linked_after_later_lead(tmp_path):
    import csv
    event_dir = tmp_path / "events"
    event_dir.mkdir()
    event_file = event_dir / "events_0001.jsonl"
    event = {
        "event_id": "e-1", "event_type": "call.initiated",
        "workflow_id": "motor_renewal", "call_id": "c-1",
        "occurred_at": "2026-10-03 10:00:00",
        "phone": "9876543210", "payload": {}
    }
    event_file.write_text(json.dumps(event) + "\n")
    conn = pipeline.connect(tmp_path / "ledger.sqlite")
    pipeline.ingest_events_file(conn, event_file)
    pipeline.build_report(conn, tmp_path / "reports_before")
    before = json.loads((tmp_path / "reports_before" / "data_quality.json").read_text())
    assert before["orphan_events"] == 1

    lead_dir = tmp_path / "leads"
    lead_dir.mkdir()
    lead_file = lead_dir / "batch_001.csv"
    lead_file.write_text(
        "customer_name,phone,policy_number\n"
        "Test Customer,9876543210,POL-1\n"
    )
    schema = pipeline.load_schemas()["motor_renewal"]
    pipeline.ingest_lead_file(conn, lead_file, "motor_renewal", schema)
    pipeline.build_report(conn, tmp_path / "reports_after")
    after = json.loads((tmp_path / "reports_after" / "data_quality.json").read_text())
    assert after["orphan_events"] == 0
    assert after["lead_rows_total"] == 1

    # Re-ingestion is a no-op, including quality counters.
    pipeline.ingest_lead_file(conn, lead_file, "motor_renewal", schema)
    assert pipeline.get_count(conn, "lead_rows_total") == 1
    conn.close()
