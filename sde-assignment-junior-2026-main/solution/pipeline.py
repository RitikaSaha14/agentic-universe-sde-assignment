from __future__ import annotations
import argparse, csv, hashlib, hmac, json, os, re, sqlite3
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from cryptography.fernet import Fernet
from zoneinfo import ZoneInfo

IST=ZoneInfo("Asia/Kolkata")
SCHEMA_DIR=Path(__file__).resolve().parents[1]/"assignment-a-data"/"schemas"

def key_material():
    raw=os.environ.get("LEDGER_ENCRYPTION_KEY")
    if not raw:
        # Local-development fallback. Set a private key in production.
        raw="local-development-only-change-this-key"
    return hashlib.sha256(raw.encode()).digest()

def cipher():
    return Fernet(__import__("base64").urlsafe_b64encode(key_material()))

def encrypt(value):
    return cipher().encrypt(str(value).encode()).decode()

def decrypt(value):
    return cipher().decrypt(value.encode()).decode()

def phone_normalize(value):
    digits=re.sub(r"\D","",str(value or ""))
    if len(digits)==12 and digits.startswith("91"): digits=digits[2:]
    elif len(digits)==11 and digits.startswith("0"): digits=digits[1:]
    if len(digits)!=10 or digits[0] not in "6789": return None
    return "+91"+digits

def phone_hash(phone):
    return hmac.new(key_material(),phone.encode(),hashlib.sha256).hexdigest()

def parse_date(value):
    s=str(value or "").strip()
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%d-%b-%Y"):
        try: return datetime.strptime(s,fmt).date().isoformat()
        except ValueError: pass
    raise ValueError("invalid_date")

def parse_decimal(value):
    s=str(value or "").strip()
    s=re.sub(r"^(?:₹|Rs\.?|INR)\s*","",s,flags=re.I).replace(",","")
    try: d=Decimal(s)
    except InvalidOperation: raise ValueError("invalid_decimal")
    if not d.is_finite() or d<0: raise ValueError("invalid_decimal")
    return str(d.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP))

def parse_timestamp(value):
    s=str(value)
    if s.endswith("Z"): dt=datetime.fromisoformat(s[:-1]+"+00:00")
    else: dt=datetime.fromisoformat(s)
    if dt.tzinfo is None: dt=dt.replace(tzinfo=IST)
    return dt.astimezone(IST)

def norm_header(s): return re.sub(r"[_\s]+"," ",str(s).strip().lower())

def load_schemas():
    out={}
    for p in sorted(SCHEMA_DIR.glob("*.json")):
        d=json.loads(p.read_text(encoding="utf-8")); out[d["workflow_id"]]=d
    return out

def connect(db):
    c=sqlite3.connect(db)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS processed_files(
      file_key TEXT PRIMARY KEY, kind TEXT NOT NULL, source TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS leads(
      id INTEGER PRIMARY KEY, workflow_id TEXT NOT NULL, phone_hash TEXT NOT NULL,
      phone_enc TEXT NOT NULL, name_enc TEXT, fields_json TEXT NOT NULL,
      batch_id TEXT NOT NULL, UNIQUE(workflow_id,phone_hash));
    CREATE TABLE IF NOT EXISTS events(
      event_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, call_id TEXT NOT NULL,
      phone_hash TEXT, data_enc TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS counters(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS rejections(
      workflow_id TEXT,batch_id TEXT,row_number INTEGER,reason TEXT);
    CREATE TABLE IF NOT EXISTS batches(
      workflow_id TEXT NOT NULL,batch_id TEXT NOT NULL,
      PRIMARY KEY(workflow_id,batch_id));
    CREATE INDEX IF NOT EXISTS events_phone_idx ON events(workflow_id,phone_hash);
    CREATE INDEX IF NOT EXISTS events_call_idx ON events(workflow_id,call_id);
    """)
    return c

def count(c,k,n=1):
    c.execute("INSERT INTO counters(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=value+excluded.value",(k,n))
def get_count(c,k): 
    r=c.execute("SELECT value FROM counters WHERE key=?",(k,)).fetchone()
    return r["value"] if r else 0

def file_key(path):
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    return str(path.resolve())+"|"+h

def already(c,path):
    return c.execute("SELECT 1 FROM processed_files WHERE file_key=?",(file_key(path),)).fetchone() is not None
def mark(c,path,kind):
    c.execute("INSERT OR IGNORE INTO processed_files VALUES(?,?,?)",(file_key(path),kind,str(path)))

def read_schemas(c):
    schemas=load_schemas()
    dispositions={}
    with open(SCHEMA_DIR/"dispositions.csv",encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            dispositions.setdefault(r["workflow_id"],{})[r["code"]]={"terminal":r["is_terminal"].lower()=="true","success":r["is_success"].lower()=="true"}
    return schemas,dispositions

def parse_field(v,field):
    s=str(v or "").strip()
    if not s: return None
    typ=field["type"]
    if typ=="string": return s
    if typ=="phone": 
        p=phone_normalize(s)
        if not p: raise ValueError("invalid_phone")
        return p
    if typ=="date": return parse_date(s)
    if typ=="decimal": return parse_decimal(s)
    if typ=="enum":
        vals={x.lower() for x in field["values"]}
        if s.lower() not in vals: raise ValueError("invalid_enum")
        return s.lower()
    return s

def ingest_lead_file(c,path,wf,schema):
    if already(c,path): return
    c.execute("INSERT OR IGNORE INTO batches(workflow_id,batch_id) VALUES(?,?)",(wf,path.stem))
    fields=schema["fields"]
    aliases={}
    for f in fields:
        for h in [f["name"]]+f.get("aliases",[]): aliases[norm_header(h)]=f["name"]
    with open(path,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        mapped={}
        for h in reader.fieldnames or []:
            target=aliases.get(norm_header(h))
            if target: mapped[h]=target
        rownum=0
        for row in reader:
            if not any(str(v or "").strip() for v in row.values()): continue
            rownum+=1; count(c,"lead_rows_total")
            values={f["name"]:None for f in fields}
            errors={}
            warnings=0
            for col,target in mapped.items():
                raw=row.get(col)
                fld=next(x for x in fields if x["name"]==target)
                try: values[target]=parse_field(raw,fld)
                except ValueError as exc:
                    values[target]=None
                    if fld["type"]=="phone" and str(raw or "").strip():
                        errors[target]="invalid_phone"
                    elif not fld.get("required") and str(raw or "").strip():
                        warnings+=1
            reason=None
            # The first failure is determined strictly by schema order.
            for fld in fields:
                name=fld["name"]
                if name in errors:
                    reason=errors[name]; break
                if fld.get("required") and values.get(name) is None:
                    reason="missing_required:"+name; break
            batch=path.stem
            if reason:
                count(c,"lead_rows_rejected")
                count(c,"reason:"+reason)
                c.execute("INSERT INTO rejections(workflow_id,batch_id,row_number,reason) VALUES(?,?,?,?)",(wf,batch,rownum,reason))
                continue
            count(c,"field_warnings",warnings)
            phone=values["phone"]; ph=phone_hash(phone)
            old=c.execute("SELECT id,fields_json,name_enc FROM leads WHERE workflow_id=? AND phone_hash=?",(wf,ph)).fetchone()
            pii_name=values.pop("customer_name",None)
            values.pop("phone",None)
            if old:
                count(c,"duplicate_lead_rows_merged")
                merged=json.loads(old["fields_json"])
                for k,v in values.items():
                    if v is not None: merged[k]=v
                name_enc=encrypt(pii_name) if pii_name is not None else old["name_enc"]
                c.execute("UPDATE leads SET fields_json=?,name_enc=? WHERE id=?",(json.dumps(merged),name_enc,old["id"]))
            else:
                c.execute("INSERT INTO leads(workflow_id,phone_hash,phone_enc,name_enc,fields_json,batch_id) VALUES(?,?,?,?,?,?)",
                          (wf,ph,encrypt(phone),encrypt(pii_name) if pii_name is not None else None,json.dumps(values),batch))
    mark(c,path,"leads")

def ingest_events_file(c,path):
    if already(c,path): return
    with open(path,encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            count(c,"events_total")
            try:
                e=json.loads(line)
                if not isinstance(e,dict) or not e.get("event_id"): raise ValueError()
            except Exception:
                count(c,"malformed_events"); continue
            if c.execute("SELECT 1 FROM events WHERE event_id=?",(str(e["event_id"]),)).fetchone():
                count(c,"duplicate_events_dropped"); continue
            ph=None
            if e.get("phone"):
                p=phone_normalize(e["phone"])
                if p: ph=phone_hash(p)
            c.execute("INSERT INTO events(event_id,workflow_id,call_id,phone_hash,data_enc) VALUES(?,?,?,?,?)",
                      (str(e["event_id"]),str(e.get("workflow_id","")),str(e.get("call_id","")),ph,encrypt(json.dumps(e))))
    mark(c,path,"events")

def ingest_drop(c,drop):
    schemas,_=read_schemas(c)
    # Files are deliberately ordered by workflow then filename.
    leads=drop/"leads"
    if leads.exists():
        for wfdir in sorted(p for p in leads.iterdir() if p.is_dir()):
            wf=wfdir.name
            if wf not in schemas: continue
            for p in sorted(wfdir.glob("*.csv")): ingest_lead_file(c,p,wf,schemas[wf])
    evdir=drop/"events"
    if evdir.exists():
        for p in sorted(evdir.glob("*.jsonl")): ingest_events_file(c,p)

def build_report(c,out):
    schemas,dispos=read_schemas(c)
    leads=c.execute("SELECT * FROM leads ORDER BY workflow_id, id").fetchall()
    lead_by_hash={(l["workflow_id"],l["phone_hash"]):l for l in leads}
    events=[]
    for r in c.execute("SELECT * FROM events"):
        try: e=json.loads(decrypt(r["data_enc"]))
        except Exception: continue
        events.append((r,e))
    # Resolve calls to lead via any phone-bearing event; override events resolve through call_id.
    call_lead={}
    linked={}
    for r,e in events:
        key=(e.get("workflow_id",""),e.get("call_id",""))
        if r["phone_hash"] and (e.get("workflow_id"),r["phone_hash"]) in lead_by_hash:
            call_lead[key]=lead_by_hash[(e["workflow_id"],r["phone_hash"])]["id"]
    # Ordinary events link by their own phone. Only supervisor overrides use call_id.
    for r,e in events:
        key=(e.get("workflow_id",""),e.get("call_id",""))
        if e.get("event_type")=="disposition.override":
            lid=call_lead.get(key)
        else:
            lid=None
            if r["phone_hash"]:
                lead=lead_by_hash.get((e.get("workflow_id",""),r["phone_hash"]))
                lid=lead["id"] if lead else None
        if lid is not None:
            linked.setdefault(lid,[]).append(e)
    # Disposition validation occurs after orphan resolution.
    valid_events={}
    unknown=0
    for lid,es in linked.items():
        valid=[]
        for e in es:
            typ=e.get("event_type","")
            if typ.startswith("disposition."):
                code=(e.get("payload") or {}).get("disposition_code")
                if code not in dispos.get(e.get("workflow_id"),{}):
                    unknown+=1; continue
            valid.append(e)
        valid_events[lid]=valid
    # Quality counters are dynamic final-state counts.
    total_events=len(events)
    orphan=0
    for r,e in events:
        if e.get("event_type")=="disposition.override":
            is_linked=(e.get("workflow_id",""),e.get("call_id","")) in call_lead
        else:
            is_linked=bool(r["phone_hash"] and (e.get("workflow_id",""),r["phone_hash"]) in lead_by_hash)
        if not is_linked: orphan+=1
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    # Prepare per-lead derived facts and report rows.
    batch_rows=[]; daily={}
    lead_rows=[]
    buckets={}
    for l in leads:
        wf=l["workflow_id"]; data=json.loads(l["fields_json"])
        for fld in schemas[wf]["fields"]:
            if fld.get("default") is not None and data.get(fld["name"]) is None:
                data[fld["name"]]=fld["default"]
        phone=decrypt(l["phone_enc"])
        es=valid_events.get(l["id"],[])
        calls={}
        for e in es:
            typ=e.get("event_type"); cid=e.get("call_id")
            if typ=="call.initiated":
                try: ts=parse_timestamp(e["occurred_at"])
                except Exception: continue
                calls.setdefault(cid,{})["initiated"]=ts
            elif typ in ("call.connected","call.telephony_failed"):
                calls.setdefault(cid,{})[typ]=True
            elif typ in ("disposition.set","disposition.override"):
                try: ts=parse_timestamp(e["occurred_at"])
                except Exception: continue
                calls.setdefault(cid,{}).setdefault("dispositions",[]).append((typ,ts,(e.get("payload") or {}).get("disposition_code")))
        # A call exists only with an initiated event.
        calls={cid:v for cid,v in calls.items() if "initiated" in v}
        dispositions={}
        for cid,v in calls.items():
            code=effective_disposition(v.get("dispositions",[]))
            if code: dispositions[cid]=code
        n=len(calls); connected=sum(bool(v.get("call.connected")) for v in calls.values())
        bucket=lead_bucket(calls,dispositions,dispos[wf])
        buckets.setdefault((wf,l["batch_id"]),[]).append(bucket)
        ordered=sorted(calls.items(),key=lambda kv:kv[1]["initiated"])
        last=ordered[-1][1]["initiated"] if ordered else None
        current=next((dispositions[cid] for cid,v in reversed(ordered) if cid in dispositions),"")
        ever=any(dispos[wf].get(code,{}).get("success",False) for code in dispositions.values())
        lead_rows.append([wf,data.get(next(f["name"] for f in schemas[wf]["fields"] if f.get("reference")),""),l["batch_id"],
                          "+91******"+phone[-4:],bucket,n,connected,last.isoformat() if last else "",current or "",str(ever).lower()])
        for cid,v in calls.items():
            d=v["initiated"].date().isoformat()
            agg=daily.setdefault((wf,d),{"calls":0,"connected":0,"success":set()})
            agg["calls"]+=1
            if v.get("call.connected"): agg["connected"]+=1
            if dispos[wf].get(dispositions.get(cid),{}).get("success",False): agg["success"].add(l["id"])
    all_batches={(r["workflow_id"],r["batch_id"]) for r in c.execute("SELECT workflow_id,batch_id FROM batches")}
    all_batches.update(buckets)
    for wf,batch in sorted(all_batches):
        bs=buckets.get((wf,batch),[])
        batch_rows.append([wf,batch,len(bs),bs.count("yet_to_reach_out"),bs.count("in_progress_telephony_failed"),bs.count("in_progress_dialed"),bs.count("completed")])
    def write(name,header,rows):
        with open(out/name,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f,lineterminator="\n"); w.writerow(header); w.writerows(rows)
    write("batch_summary.csv",["workflow_id","batch_id","total_leads","yet_to_reach_out","in_progress_telephony_failed","in_progress_dialed","completed"],batch_rows)
    daily_rows=[[wf,d,a["calls"],a["connected"],f'{a["connected"]/a["calls"]:.4f}',len(a["success"])] for (wf,d),a in sorted(daily.items())]
    write("daily_overview.csv",["workflow_id","date","total_calls","connected_calls","connectivity_rate","success_leads"],daily_rows)
    write("lead_report.csv",["workflow_id","external_ref","batch_id","phone_masked","bucket","total_calls","connected_calls","last_call_at","current_disposition","ever_success"],sorted(lead_rows,key=lambda r:(r[0],r[1])))
    rejects=c.execute("SELECT workflow_id,batch_id,row_number,reason FROM rejections ORDER BY workflow_id,batch_id,row_number").fetchall()
    write("rejections.csv",["workflow_id","batch_id","row_number","reason"],[list(r) for r in rejects])
    reasons={}
    for r in c.execute("SELECT key,value FROM counters WHERE key LIKE 'reason:%'"):
        reasons[r["key"][7:]]=r["value"]
    quality={"lead_rows_total":get_count(c,"lead_rows_total"),"lead_rows_rejected":get_count(c,"lead_rows_rejected"),
      "rejections_by_reason":dict(sorted(reasons.items())),"duplicate_lead_rows_merged":get_count(c,"duplicate_lead_rows_merged"),
      "field_warnings":get_count(c,"field_warnings"),"events_total":get_count(c,"events_total"),
      "malformed_events":get_count(c,"malformed_events"),"duplicate_events_dropped":get_count(c,"duplicate_events_dropped"),
      "orphan_events":orphan,"unknown_disposition_events":unknown}
    (out/"data_quality.json").write_text(json.dumps(quality,indent=2)+"\n",encoding="utf-8")


def effective_disposition(dispositions_for_call):
    """Return the latest override, else latest set; input tuples are (type, timestamp, code)."""
    overrides=[x for x in dispositions_for_call if x[0]=="disposition.override"]
    sets=[x for x in dispositions_for_call if x[0]=="disposition.set"]
    chosen=max(overrides,key=lambda x:x[1]) if overrides else (max(sets,key=lambda x:x[1]) if sets else None)
    return chosen[2] if chosen else None

def lead_bucket(call_facts, disposition_codes, catalogue):
    """call_facts maps call_id to facts; only initiated calls belong in this mapping."""
    if not call_facts: return "yet_to_reach_out"
    if any(catalogue.get(code,{}).get("terminal",False) for code in disposition_codes.values()):
        return "completed"
    if all(f.get("call.telephony_failed",False) for f in call_facts.values()):
        return "in_progress_telephony_failed"
    return "in_progress_dialed"

def main():
    ap=argparse.ArgumentParser(description="Interaction ledger pipeline")
    ap.add_argument("--db",default="data/ledger.sqlite")
    sub=ap.add_subparsers(dest="command",required=True)
    ing=sub.add_parser("ingest"); ing.add_argument("drop")
    rep=sub.add_parser("report"); rep.add_argument("--out",default="reports")
    args=ap.parse_args()
    Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    c=connect(args.db)
    c.execute("CREATE TABLE IF NOT EXISTS rejections(workflow_id TEXT,batch_id TEXT,row_number INTEGER,reason TEXT)")
    if args.command=="ingest":
        ingest_drop(c,Path(args.drop)); c.commit()
    else:
        build_report(c,args.out)
    c.close()
if __name__=="__main__": main()
