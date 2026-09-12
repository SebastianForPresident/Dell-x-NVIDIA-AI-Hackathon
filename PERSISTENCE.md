# Authoritative investigation persistence

React/FastAPI and agent tools now share InvestigationService. The active API does
not read or write the legacy `cases` collection. Existing documents there are
preserved; they are not automatically copied or duplicated into investigations.

## Configuration

Use only MONGODB_URI and MONGODB_DATABASE; optionally CROP_ASSET_DIR for retained
local assets. `.env` is not loaded automatically. See README.md for startup.

## Data model

The service uses `claims`, `investigations`, `evidence`, `agent_actions`, `follow_up_tasks`, and `reports` collections. All `_id` values are strings, child documents reference `investigation_id`, and timestamps are UTC BSON dates. A content-derived investigation ID preserves changed-evidence history; repeat writes for the same evidence or task are idempotent. `save_package` publishes its completion marker only after child records are saved, so retrying after an interrupted save can finish the package. Cross-collection writes are not transactional.

`start_investigation` registers a claim and input snapshot. `record_evidence` stores a structured finding; `record_action` stores a tool-call audit record. `create_follow_up_task`, `resolve_follow_up_task`, and `set_case_status` manage review workflow. `save_report` and `load_package` save and reopen a report. The service does not make an insurance decision or run an autonomous agent.

The API retains uploaded PDF, CSV and GeoTIFF assets under CROP_ASSET_DIR. MongoDB stores asset manifests and findings, not raster bytes. Reports and boundaries must fit document limits. Keep both the MongoDB data volume and asset directory across restarts.

## Tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Persistence tests use `mongomock` to cover reopening, changed-input history, duplicate saves and tasks, status gates, invalid actions, and interrupted-save recovery. These tests do not establish real MongoDB connectivity or GB10 compatibility. Use the [README](README.md) for the current unified React/FastAPI setup. OpenClaw registration remains pending.
