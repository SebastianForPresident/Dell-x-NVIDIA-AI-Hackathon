# Investigation history module

`investigations.py` and `persistence.py` provide an optional MongoDB-backed investigation history service. They came from the earlier Streamlit implementation. The current React/FastAPI website does **not** call this service: it stores cases and reports in the `cases` collection through `server/database.py`. Follow-up tasks, action records, and the status workflow described here are available in Python but are not yet exposed in the website.

## Configuration

The website uses `MONGO_URI` and `MONGO_DB` (see `.env.example`). The standalone history module uses `MONGODB_URI` and `MONGODB_DATABASE` in `MongoStore.from_env()`. If using both against the same local database, set both pairs to the same values. `.env` is not loaded automatically.

```python
from investigations import InvestigationService
from persistence import MongoStore

service = InvestigationService(MongoStore.from_env())
```

## Data model

The service uses `claims`, `investigations`, `evidence`, `agent_actions`, `follow_up_tasks`, and `reports` collections. All `_id` values are strings, child documents reference `investigation_id`, and timestamps are UTC BSON dates. A content-derived investigation ID preserves changed-evidence history; repeat writes for the same evidence or task are idempotent. `save_package` publishes its completion marker only after child records are saved, so retrying after an interrupted save can finish the package. Cross-collection writes are not transactional.

`start_investigation` registers a claim and input snapshot. `record_evidence` stores a structured finding; `record_action` stores a tool-call audit record. `create_follow_up_task`, `resolve_follow_up_task`, and `set_case_status` manage review workflow. `save_report` and `load_package` save and reopen a report. The service does not make an insurance decision or run an autonomous agent.

Uploaded PDF, CSV, and GeoTIFF bytes are not archived by this module. Reports and boundaries still need to fit MongoDB document limits. The website likewise processes rasters from temporary files and stores source names and hashes rather than raw rasters.

## Tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Persistence tests use `mongomock` to cover reopening, changed-input history, duplicate saves and tasks, status gates, invalid actions, and interrupted-save recovery. These tests do not establish real MongoDB connectivity or GB10 compatibility. Use the [README](README.md) for the current React/FastAPI setup and OpenShell/Qwen instructions.
