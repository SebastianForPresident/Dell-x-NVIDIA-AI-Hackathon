# Agent-facing assembly layer

**Assembly update:** React/FastAPI now uses these investigation records directly.
See [ASSEMBLY.md](ASSEMBLY.md) for current endpoints, retained assets, and startup.
The incoming-frontend-gap section below describes the earlier milestone and is
superseded by that handoff. Tool schemas/invoke remain compatible; trusted callers
may specify `actor="demo"` for explicit deterministic runs (default remains agent).

Started at `e64e53350eef8732f278ca408a8279cb1e0eae8e`. During implementation,
upstream advanced through `75eddca` to `a1159f043f2951f7202d6497ce94a66181d6dcc9`.
Those React/FastAPI changes were fast-forwarded without conflicts or overwriting
local changes. This layer remains independent of either UI.

## Runtime boundary

`AgentTools.start(service, metadata, assets)` is a trusted application call, not
a model tool. It creates/reuses an investigation with an immutable asset manifest.
Metadata requires `claim_id`, `reported_cause`, `reported_loss_date` (ISO date),
`field`, `claimed_crop`, and explicit boolean `synthetic_demo`. Optional location
and other intake fields are retained. Use the actual DeWitt claim and its local
clipped evidence when available; no real Illinois dataset is checked into this
revision. The tests fabricate small Illinois fixtures and label them synthetic.

```python
from pathlib import Path
from agent_assets import CaseAssets
from agent_tools import AgentTools
from investigations import InvestigationService
from persistence import MongoStore

service = InvestigationService(MongoStore.from_env())
# Set MONGODB_URI and MONGODB_DATABASE before running this application code.
assets = CaseAssets(
    root=Path('/path/to/approved/case-directory'),
    boundary='field.geojson', weather='weather.csv', crop='crop.tif',
    before='before.tif', after='after.tif',
    before_date='2026-05-30', after_date='2026-08-12',
    selected_field=0, red_band=1, nir_band=2, weather_unit='mm',
)
tools = AgentTools.start(service, {
    'claim_id': 'DEWITT-DEMO-1', 'reported_cause': 'Drought',
    'reported_loss_date': '2026-07-18', 'field': 'Claimed corn field',
    'claimed_crop': 'Corn', 'synthetic_demo': True,
    'location': 'DeWitt County, Illinois',
}, assets)

schemas = tools.schemas()
# Example direct handler smoke test, NOT autonomous inference:
result = tools.invoke('check_rainfall', {}, call_id='runtime-call-001')
```

Use `AgentTools(service, investigation_id, assets)` to reopen an existing agent
investigation; its manifest must match. Each new call verifies content hashes.
Large statewide rasters should be clipped ahead of time: hashing every registered
asset for each new tool call favors correctness over large-dataset performance.
Missing assets are represented by `None`; a configured but nonexistent file is a
configuration error. Missing evidence returns a persisted `unavailable` finding.

## Exact schemas and deterministic mapping

`schemas()` returns a fresh JSON-serializable list of `{name, description,
input_schema}` objects. Every input schema is an object with
`additionalProperties: false`; all listed properties are required.

| Tool | Arguments | Implementation |
| --- | --- | --- |
| `get_claim` | `{}` | `InvestigationService.load_package`; returns investigation metadata, status, findings, open tasks |
| `check_crop_classification` | `{}` | `load_boundary`, `crop_finding`; expected crop comes from registered claim |
| `check_rainfall` | `{}` | `parse_weather`, `weather_finding`; date and cause come from registered claim |
| `check_vegetation_change` | `{}` | `load_boundary`, `ndvi_mean`, `vegetation_finding` |
| `compare_neighboring_fields` | `{}` | `load_boundary`, `ndvi_mean`, `neighbors_finding`; adds coverage/date safeguards |
| `create_follow_up_task` | `{"title": string, "reason": string}` | Service task creation and NEEDS_EVIDENCE transition |
| `set_case_status` | `{"status": enum, "reason": string}` | Service transition validation |
| `save_investigation_report` | `{}` | Service `publish_agent_report`; `Finding`, `build_report`, `save_report` |

Title/reason strings have `minLength: 1`, `maxLength: 1000`; whitespace-only text
is rejected by the handler. Status enum is exactly `INVESTIGATING`,
`NEEDS_EVIDENCE`, `READY_FOR_ADJUSTER_REVIEW`. The model supplies neither case IDs,
file paths, measured values, free-form report facts, nor an actor identity.

`invoke(name, arguments, call_id)` accepts a runtime-controlled call ID matching
`[A-Za-z0-9_.:-]{1,128}`. Arguments must be finite JSON, at most 5000 characters.
Success is `{"ok": true, "data": {...}}`; a handler failure is
`{"ok": false, "error": {"code": "...", "message": "..."}}`.
Evidence-tool data contains `evidence_id` and `finding`. Report data contains
`report_id` and the structured report. Task data contains `task_id`, `task_status`,
and current investigation `status`. Transport validation errors (invalid call ID,
non-JSON or oversized input) raise before dispatch. Schema/execution failures are
audited, including attempts at unknown tools or illegal workflow actions.

## Persistence and workflow safeguards

- All agent database operations go through `InvestigationService`.
- Findings go to `evidence`; full call arguments and structured results go to
  `agent_actions` with `actor="agent"`. Failed calls have `ok=false` results.
- Stable call IDs replay stored responses. Reusing an ID with different inputs
  returns and audits `CALL_ID_CONFLICT`. Use a new call ID to retry a failed result.
- Evidence, tasks, and reports use existing content-derived IDs. A crash between
  a side effect and its audit can be retried without duplicating the side effect.
  Audit-write failures raise instead of returning an unaudited success.
- Reports are built only from exactly one persisted finding in each of the four
  evidence categories. They carry evidence IDs, then the service publishes the
  report pointer and completion flag. No report facts come from LLM text.
- Agent readiness requires a current report matching all four evidence records,
  all four statuses `supported`, and no open tasks. This is deliberately conservative:
  conflicting/inconclusive evidence requires human follow-up, not model dismissal.
- NEW moves to INVESTIGATING on the first business/evidence call. Allowed agent
  transitions are NEW -> INVESTIGATING; INVESTIGATING -> NEEDS_EVIDENCE or READY;
  NEEDS_EVIDENCE -> INVESTIGATING or READY; READY -> NEEDS_EVIDENCE. Same-state calls
  are idempotent. READY always means adjuster review, never claim approval.
- Task resolution remains a human/application service action, not a model tool.
  Re-requesting an already resolved identical task does not reopen it or regress
  the case's status. Changed assets require a new investigation.
- Run one writer per investigation. Existing multi-collection writes are not a
  transaction and these handlers do not promise concurrent exactly-once execution.

## Remaining OpenClaw integration

No OpenClaw API has been invented and no second autonomous loop was added.
On GB10, verify the installed 2026.9.4 registration/invocation mechanism. Then:

1. Register only `schemas()` and map callbacks to the case-bound `invoke` method.
2. Pass runtime tool-call IDs through unchanged (or map them to accepted stable IDs).
3. Return the structured tool result to OpenClaw so the model chooses the next call.
4. Configure and verify OpenClaw -> local Ollama -> `gpt-oss:20b`, including tool
   calling and no cloud fallback. Do not assume a `/v1` compatibility route works.
5. Demonstrate one model-chosen evidence call, MongoDB audit/evidence writes, and
   the result returned to the model before attempting the whole claim.

## Incoming frontend integration gaps

The merged FastAPI backend uses its own `cases` collection and `MONGO_URI` /
`MONGO_DB`; the service uses `MONGODB_URI` / `MONGODB_DATABASE`. Configure them to
the same server/database, or construct `InvestigationService(MongoStore(database))`
inside trusted backend code. This task does not migrate or overwrite `cases`.
The frontend still needs a claim-to-investigation mapping and a read projection of
service status/tasks/audit. Its upload rasters are temporary, so retain approved
case files for the agent's lifetime before binding assets.

The teammate seed cases are NY examples and the new backend still exposes legacy
OpenShell/Qwen inference routes. These were preserved, not adopted by this layer.
Supply actual local DeWitt evidence and update that runtime wiring next. No dataset
downloads, model calls, frontend rewrite, or inference configuration changes occurred.

## Validation / deployment

`python -m unittest discover -s tests -v` exercises real Rasterio calculations on
tiny synthetic files with mongomock persistence. New tests cover complete drought
workflow, evidence/audit storage, invalid inputs, retries, changed assets, path
escape, follow-up tasks, conflicts, readiness gates, and visible execution errors.
The two obsolete Streamlit UI tests are explicitly skipped because upstream removed
`app.py`; the teammate seed test and original GIS/persistence tests still run.

No new dependencies were added. Python 3.12 and Linux ARM64 Rasterio/GDAL/PyMongo
availability still need GB10 verification. Live MongoDB, the React/FastAPI runtime,
and local inference were not exercised by this mocked tool-layer suite. Existing
Docker/OpenShell wiring is not proof of OpenClaw deployment compatibility.
