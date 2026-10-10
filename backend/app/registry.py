from __future__ import annotations
import json, sqlite3, uuid
from pathlib import Path
from typing import Any
from jsonschema import Draft7Validator

BASE_DIR = Path(__file__).resolve().parents[2]
SEED_DIR = BASE_DIR / "sample_input" / "rules"
DB_PATH = Path(__import__("os").environ.get("RULES_DB_PATH", str(BASE_DIR / "rules.db")))
ALLOWED_OPS = {"var", "and", "or", "!", "==", "!=", ">", ">=", "<", "<=", "in", "regex", "if", "toNumber", "substr"}

def _connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_registry():
    with _connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS rule_sets (
            id TEXT NOT NULL, version INTEGER NOT NULL, display_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', regulator TEXT, jurisdiction TEXT,
            rules_json TEXT NOT NULL, source TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(id, version))""")
        con.execute("CREATE TABLE IF NOT EXISTS active_rule_sets (id TEXT PRIMARY KEY, version INTEGER NOT NULL)")
    # Seed once; never overwrite a user's registry on restart.
    with _connect() as con:
        existing = con.execute("SELECT COUNT(*) FROM rule_sets").fetchone()[0]
    if existing == 0:
        for path in sorted(SEED_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                validate_rule_set(payload)
                set_id = str(payload.get("rule_set_id") or payload.get("regulator") or path.stem).strip()
                payload.setdefault("rule_set_id", set_id)
                payload.setdefault("display_name", payload.get("regulator", set_id))
                payload.setdefault("description", f"Seed rules imported from {path.name}")
                # Source definitions remain unchanged. Ambiguous applicability is reported, not guessed.
                save_rule_set(payload, source=f"seed:{path.name}", replace_active=True)
            except Exception as exc:
                # Startup must remain available; malformed seed is surfaced via health/metadata.
                print(f"WARNING: skipped invalid seed {path.name}: {exc}")

def _walk_ops(node: Any):
    if isinstance(node, dict):
        for key, value in node.items():
            if key not in ALLOWED_OPS:
                raise ValueError(f"Unsupported operator or key in condition: {key}")
            yield key
            yield from _walk_ops(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_ops(item)

def validate_rule_set(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object.")
    rules = payload.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("Rule set must contain a non-empty 'rules' array.")
    seen = set()
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule at index {i} must be an object.")
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError(f"Rule at index {i} is missing a non-empty id.")
        if rid in seen:
            raise ValueError(f"Duplicate rule ID inside upload: {rid}")
        seen.add(rid)
        if "logic" not in rule:
            raise ValueError(f"Rule {rid} is missing 'logic'.")
        _walk_ops(rule["logic"])
        if "applies_when" in rule:
            _walk_ops(rule["applies_when"])
    payload.setdefault("rule_set_id", payload.get("regulator") or "CUSTOM")
    payload.setdefault("display_name", payload.get("regulator") or payload["rule_set_id"])
    payload.setdefault("description", "User-imported rule set")
    if not isinstance(payload["rule_set_id"], str) or not payload["rule_set_id"].strip():
        raise ValueError("rule_set_id must be a non-empty string.")
    return payload

def save_rule_set(payload: dict, source: str = "upload", replace_active: bool = True) -> dict:
    payload = validate_rule_set(payload)
    set_id = payload["rule_set_id"].strip()
    rules = payload["rules"]
    # Rule IDs are unique across active sets to prevent ambiguous references.
    with _connect() as con:
        if not replace_active:
            current = con.execute("SELECT version FROM active_rule_sets WHERE id=?", (set_id,)).fetchone()
            if current:
                return {"id": set_id, "version": current["version"], "status": "already_seeded"}
        active_ids = con.execute("""SELECT rs.rules_json FROM rule_sets rs
            JOIN active_rule_sets a ON a.id=rs.id AND a.version=rs.version""").fetchall()
        for row in active_ids:
            for existing in json.loads(row["rules_json"]).get("rules", []):
                if any(r["id"] == existing["id"] for r in rules):
                    # Same rule set update can retain IDs; cross-set duplicate IDs are rejected.
                    active = con.execute("SELECT version FROM active_rule_sets WHERE id=?", (set_id,)).fetchone()
                    if not active or existing["id"] not in {r["id"] for r in json.loads(con.execute(
                        "SELECT rules_json FROM rule_sets WHERE id=? AND version=?", (set_id, active["version"])
                    ).fetchone()["rules_json"]).get("rules", [])}:
                        raise ValueError(f"Rule ID already exists in an active rule set: {existing['id']}")
        current = con.execute("SELECT version FROM active_rule_sets WHERE id=?", (set_id,)).fetchone()
        version = (current["version"] + 1) if current else 1
        con.execute("INSERT INTO rule_sets(id,version,display_name,description,regulator,jurisdiction,rules_json,source) VALUES(?,?,?,?,?,?,?,?)",
            (set_id, version, payload["display_name"], payload["description"], payload.get("regulator"),
             payload.get("jurisdiction"), json.dumps(payload, ensure_ascii=False), source))
        if replace_active:
            con.execute("INSERT INTO active_rule_sets(id,version) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version",
                        (set_id, version))
    return {"id": set_id, "version": version, "status": "active", "rule_count": len(rules)}

def list_rule_sets():
    with _connect() as con:
        rows = con.execute("""SELECT rs.id,rs.version,rs.display_name,rs.description,rs.regulator,rs.jurisdiction,
            rs.created_at,rs.source,rs.rules_json FROM rule_sets rs
            JOIN active_rule_sets a ON a.id=rs.id AND a.version=rs.version ORDER BY rs.display_name""").fetchall()
    return [{"id": r["id"], "version": r["version"], "display_name": r["display_name"],
             "description": r["description"], "regulator": r["regulator"], "jurisdiction": r["jurisdiction"],
             "created_at": r["created_at"], "source": r["source"],
             "rule_count": len(json.loads(r["rules_json"])["rules"])} for r in rows]

def get_rule_sets(ids: list[str]):
    if not ids:
        raise ValueError("Select at least one rule set.")
    with _connect() as con:
        result = []
        for set_id in ids:
            row = con.execute("""SELECT rs.* FROM rule_sets rs JOIN active_rule_sets a
                ON a.id=rs.id AND a.version=rs.version WHERE rs.id=?""", (set_id,)).fetchone()
            if not row:
                raise ValueError(f"Unknown rule set ID: {set_id}")
            result.append(json.loads(row["rules_json"]))
    return result
