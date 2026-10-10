from __future__ import annotations
import csv, io, json, re
from datetime import datetime
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jsonschema import Draft7Validator, FormatChecker
from .registry import init_registry, list_rule_sets, save_rule_set, get_rule_sets, BASE_DIR
from .rule_engine import evaluate_rule

app = FastAPI(title="Reg IRIS Impact Matrix API", version="0.1.0",
              description="Dynamic JSON-rule validation for trade CSVs.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SCHEMA_PATH = BASE_DIR / "sample_input" / "schema" / "reporting_schema.json"

@app.on_event("startup")
def startup():
    init_registry()

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "reg-iris-impact-matrix"}

@app.get("/api/rules")
def rules():
    return {"rule_sets": list_rule_sets()}

@app.post("/api/rules")
async def upload_rules(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(400, "Upload a .json rule-set file.")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "JSON upload exceeds 2 MB.")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        result = save_rule_set(payload, source=f"upload:{file.filename}")
        return {"message": "Rule set registered successfully.", **result}
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, f"Rule set rejected: {exc}")

def _load_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

def _clean(value: Any):
    if value is None: return None
    return value.strip() if isinstance(value, str) else value

def _parse_csv(raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8 encoded.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "CSV is empty or has no header row.")
    headers = [h.strip() for h in reader.fieldnames if h is not None]
    if len(set(headers)) != len(headers):
        raise HTTPException(422, "CSV contains duplicate column names.")
    schema = _load_schema()
    required = set(schema.get("required", []))
    missing = sorted(required - set(headers))
    if missing:
        raise HTTPException(422, "CSV is missing required columns: " + ", ".join(missing))
    records = []
    for index, raw_record in enumerate(reader, start=2):
        if None in raw_record:
            raise HTTPException(422, f"CSV row {index} has more values than the header.")
        record = {str(k).strip(): _clean(v) for k, v in raw_record.items() if k is not None}
        records.append((index, record))
    if not records:
        raise HTTPException(422, "CSV contains a header but no trade records.")
    return records, schema

def _schema_issues(record, schema):
    # CSV values arrive as strings. Coerce only schema-declared numeric fields before validation.
    normalized = {k: v for k, v in record.items() if v not in (None, "")}
    for key, value in list(normalized.items()):
        prop = schema.get("properties", {}).get(key, {})
        typ = prop.get("type")
        try:
            if typ == "integer":
                if re.fullmatch(r"[+-]?\d+", str(value)):
                    normalized[key] = int(value)
            elif typ == "number":
                normalized[key] = float(value)
        except (ValueError, TypeError):
            pass
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    return [e.message for e in validator.iter_errors(normalized)]

@app.post("/api/impact-matrix")
async def create_matrix(file: UploadFile = File(...), rule_set_ids: str = Form(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv trade file.")
    raw = await file.read()
    if len(raw) > 20_000_000:
        raise HTTPException(413, "CSV upload exceeds 20 MB.")
    try:
        selected_ids = json.loads(rule_set_ids)
        if not isinstance(selected_ids, list) or not all(isinstance(x, str) for x in selected_ids):
            raise ValueError("rule_set_ids must be a JSON array of IDs.")
        rule_sets = get_rule_sets(selected_ids)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    records, schema = _parse_csv(raw)
    output = []
    for row_number, record in records:
        schema_errors = _schema_issues(record, schema)
        failed, evaluation_errors, skipped, passed = [], [], [], []
        for rule_set in rule_sets:
            for rule in rule_set["rules"]:
                result = evaluate_rule(rule, record)
                item = {"rule_set_id": rule_set["rule_set_id"], "rule_id": rule["id"],
                        "description": rule.get("description", ""), "reason": result.get("reason")}
                if result["status"] == "FAIL": failed.append(item)
                elif result["status"] == "ERROR": evaluation_errors.append(item)
                elif result["status"] == "SKIP": skipped.append(item)
                else: passed.append(item)
        trade_id = record.get("Trade_ID") or f"ROW-{row_number-1}"
        if evaluation_errors:
            status = "ERROR"
        elif failed or schema_errors:
            status = "FAIL"
        else:
            status = "PASS"
        output.append({"Trade_ID": trade_id, "Status": status,
            "Violated_Rules": failed,
            "Reasons": [x["reason"] for x in failed if x.get("reason")],
            "Evaluation_Errors": evaluation_errors,
            "Schema_Errors": schema_errors,
            "Skipped_Rules": [x["rule_id"] for x in skipped],
            "Passed_Rules": [x["rule_id"] for x in passed],
            "Rule_Set_Versions": {rs["rule_set_id"]: next((x["version"] for x in list_rule_sets() if x["id"] == rs["rule_set_id"]), None) for rs in rule_sets}
        })
    return {"filename": file.filename, "trade_count": len(records), "rule_set_ids": selected_ids,
            "results": output, "summary": {
                "PASS": sum(r["Status"] == "PASS" for r in output),
                "FAIL": sum(r["Status"] == "FAIL" for r in output),
                "ERROR": sum(r["Status"] == "ERROR" for r in output)}}

@app.post("/api/impact-matrix/export")
async def export_matrix(payload: dict):
    results = payload.get("results")
    if not isinstance(results, list):
        raise HTTPException(422, "Request body must contain a results array.")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["Trade_ID", "Status", "Violated_Rules", "Reasons",
        "Schema_Errors", "Evaluation_Errors", "Skipped_Rules", "Passed_Rules"], extrasaction="ignore")
    writer.writeheader()
    for result in results:
        row = dict(result)
        row["Violated_Rules"] = "; ".join(f'{x.get("rule_id")}: {x.get("reason") or x.get("description")}' for x in result.get("Violated_Rules", []))
        for key in ("Reasons", "Schema_Errors", "Evaluation_Errors", "Skipped_Rules", "Passed_Rules"):
            row[key] = "; ".join(str(x) if not isinstance(x, dict) else f'{x.get("rule_id")}: {x.get("reason")}' for x in result.get(key, []))
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="impact_matrix.csv"'})

@app.get("/api/sample-trades")
def sample_trades():
    path = BASE_DIR / "sample_input" / "trades" / "sample_trades.csv"
    if not path.exists():
        raise HTTPException(404, "Sample CSV not found.")
    return StreamingResponse(path.open("rb"), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_trades.csv"'})
