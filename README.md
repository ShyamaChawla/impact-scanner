# Reg IRIS — Impact Matrix

Reg IRIS is a dynamic regulatory trade validation starter. The UI is built with **React + Vite**, the API with **FastAPI**, and active rule-set versions are stored in **SQLite**. The supplied files are seed examples, not limits on the rules or trade files the application can accept.

## Features

- React dashboard with trade CSV upload, rule-set selection, validation summary, search, status filtering, pagination, violation details and CSV export.
- Upload JSON rule sets through the UI. The API validates supported operators, rejects duplicate IDs, and creates a new version rather than replacing historical versions.
- Independent rule interpreter with explicit applicability (`applies_when`) and PASS / FAIL / SKIP / ERROR outcomes.
- Schema validation kept distinct from regulatory-rule violations.
- Sample trade CSV and three supplied rule sets are included as seed data.
- Docker Compose setup for the React UI and FastAPI backend.
- Rule-import code is separate from validation and registry code, allowing a future plain-text/PDF importer to emit the same rule-set JSON format.

## Run with Docker (recommended)

Install Docker Desktop, then from the project root:

```powershell
docker compose up --build
```

Open:

- React UI: http://localhost:8080
- API health: http://localhost:8000/api/health
- API docs: http://localhost:8000/docs

Stop services with `Ctrl+C`, or run `docker compose down` in another terminal.

## Run locally without Docker

### Backend

From the project root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
$env:RULES_DB_PATH = "$PWD\rules.db"
uvicorn app.main:app --app-dir backend --reload --port 8000
```

### Frontend

Open a second terminal in the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (normally http://localhost:5173). Vite proxies `/api` calls to `http://localhost:8000` in development.

## API endpoints

- `GET /api/health` — health check.
- `GET /api/rules` — list active rule sets and versions.
- `POST /api/rules` — multipart `.json` upload; validates and registers a new version.
- `POST /api/impact-matrix` — multipart `file` (CSV) and `rule_set_ids` (JSON array encoded as a form string).
- `POST /api/impact-matrix/export` — JSON `{ "results": [...] }`, returns `impact_matrix.csv`.
- `GET /api/sample-trades` — supplied sample CSV.

## Rule-set JSON format

```json
{
  "rule_set_id": "CUSTOM-REGIME",
  "display_name": "Custom Regime",
  "description": "Example custom rules",
  "regulator": "Custom Regime",
  "jurisdiction": "Global",
  "rules": [
    {
      "id": "CUSTOM-1",
      "description": "Quantity must be positive",
      "logic": { ">": [{ "var": "Quantity" }, 0] },
      "impact": "Quantity must be greater than zero."
    }
  ]
}
```

Optional `applies_when` explicitly scopes a rule to records for which its expression is true:

```json
"applies_when": { "==": [{ "var": "Asset_Class" }, "Derivative"] }
```

The importer does not infer applicability from natural-language descriptions. Use explicit applicability conditions in newly authored rules when scope matters.

## Important notes about supplied seed rules

The sample rules are retained as provided; they are not silently rewritten to make their wording and expressions agree. For example, `EMIR-1` combines the derivative check and the identifier checks in one expression, so non-derivative rows may fail that expression unless applicability is made explicit in a reviewed rule-set version. `MIFID-4` attempts numeric conversion of an ISO date string; that can produce an evaluation error. Review and correct the regulatory definitions before relying on them for compliance decisions.

The schema is checked separately from selected regulatory rules. An invalid schema row is marked FAIL; a rule evaluation error takes precedence as ERROR so it cannot appear as a genuine PASS. The evaluator supports a deliberately limited JSONLogic-style subset; unsupported operators are rejected on import. Regex uses full-match semantics.

## Tests

From the project root:

```powershell
py -m pip install -r backend\requirements.txt
py -m pytest backend\tests -q
```

## Repository workflow (Windows PowerShell)

After copying/extracting this project into your cloned `impact-scanner` folder:

```powershell
git status
git add .
git commit -m "Build Reg IRIS Impact Matrix with React and FastAPI"
git push -u origin main
```

The first push creates the remote `main` branch. If Git asks for credentials, sign in using your normal GitHub authentication flow. Do not commit secrets, virtual environments, generated databases or `node_modules`.

## Before production use

Add authentication/authorization, audit logs, stricter CORS and upload controls, database backups/migrations, operational monitoring, and legal/compliance review of every rule set.
