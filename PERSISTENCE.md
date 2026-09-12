# Persistence milestone

This builds on `da29f2a`. The GIS functions and existing report structure are unchanged.
The application still runs deterministic analysis; no autonomous agent is implemented.

## Run

Install `requirements.txt` using Python 3.12 and export these variables before Streamlit:

```bash
export MONGODB_URI='mongodb://127.0.0.1:27017'
export MONGODB_DATABASE='crop_forensics'
python -m streamlit run app.py
```

PowerShell equivalents:

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017'
$env:MONGODB_DATABASE = 'crop_forensics'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

MongoDB must already be running/reachable. `.env.example` documents configuration;
it is not auto-loaded. The app uses a cached PyMongo connection, a startup ping,
and bounded connection/operation timeouts. No credentials are printed by the UI.
Without MongoDB, the existing preview still works and explicitly says it is unsaved.

Use **Save evidence package to MongoDB**, then reopen the saved investigation in
the expander. This works with the synthetic demo and uploaded evidence. Creating
a follow-up task changes status to `NEEDS_EVIDENCE`; resolving all tasks allows a
human to mark the package `READY_FOR_ADJUSTER_REVIEW`. Ready is not an insurance decision.
No automatic task generation or readiness decision is added in this milestone.

## Collections

All `_id` values are strings. Child documents reference `investigation_id`.
Timestamps are UTC BSON dates. Report payloads retain the existing JSON shape.

| Collection | Identity and contents |
| --- | --- |
| claims | `_id` = trimmed claim ID; original metadata and creation time |
| investigations | Hash of claim ID + input signature; authoritative per-investigation metadata, input/context snapshot, status, embedded transition history, complete flag, final report pointer |
| evidence | Hash of investigation + finding; structured measured finding, source, status |
| agent_actions | Hash of investigation + caller-supplied action key; tool name, arguments, result, actor; current imports are explicitly `application`, not model tool calls |
| follow_up_tasks | Hash of investigation + trimmed title/reason; OPEN/RESOLVED, actor, resolution note and timestamps |
| reports | Hash of investigation + report content; original structured report |

Built-in unique `_id` indexes prevent repeat inserts. Additional indexes support
claim history, investigation children and open tasks. Claim metadata is the first
registration; revised claim details live in each investigation's immutable snapshot.
The UI's status is always the investigation status; claims do not duplicate it.

`save_package` hashes input signature, report and context, so changed evidence
creates a new investigation rather than overwriting history. Child writes are
idempotent; the complete flag and report pointer are published last. Failed saves
can leave partial records: retrying the same package finishes them. There is no
cross-collection transaction or background recovery. Status and its transition
history update atomically in one investigation document with a status predicate.
This is intended for one active writer per investigation; concurrent readiness
and task creation across collections are not transactionally isolated.

## Streamlit integration

`app.py` calls `persistence_ui.persistence_panel(report, signature, context)`.
Session state remains an unsaved working preview and stores only a convenience
selection for saved investigations. Reopening reads MongoDB, independent of that
preview, and shows the stored report, evidence/action counts, tasks, and transitions.
Saved snapshots are explicitly separate from the current input form.

The field boundary/context and claimed crop are stored. Raw PDF/CSV/GeoTIFF uploads
are not archived: their content is represented by the existing input signature,
but rerunning GIS requires re-uploading the files. Large boundaries/reports still
need to fit MongoDB document limits; no GridFS or asset store is included.

## OpenClaw integration points (next milestone)

Use `InvestigationService(MongoStore.from_env())` outside Streamlit:

- `start_investigation(metadata, input_signature, context)` registers a claim/run.
- `get_claim(claim_id)` retrieves original claim metadata; use `load_package(id)`
  for the investigation's current metadata and state.
- `record_evidence(id, finding)` accepts the `asdict(Finding)` output of existing
  `crop_finding`, `weather_finding`, `vegetation_finding`, and `neighbors_finding`.
- Narrow wrappers will obtain validated assets and call `ndvi_mean` as needed.
- `record_action(id, action_key, tool, arguments, result, actor="agent")` stores a
  tool-call audit record; reuse the key only for retries of the same action.
- `create_follow_up_task`, `set_case_status`, `resolve_follow_up_task`, and
  `save_report` are the workflow seams. `save_report` stores a report but does not
  publish completion; the agent milestone must add its own evidence-completion
  validation before publishing a final report pointer/complete flag.

OpenClaw should choose the evidence calls/order. The current `save_package` is
only an adapter for importing the starter's deterministic output, not an agent loop.
Do not expose MongoDB or unrestricted shell access as model tools.

## GB10 / deployment gaps

- Existing Dockerfile/README inference instructions target OpenShell + Qwen. They
  are legacy, not the deployment plan for OpenClaw + Ollama + gpt-oss:20b.
- No GB10 connection was available here, so installed OpenClaw 2026.9.4 behavior
  and local model routing remain unverified. No inference configuration changed.
- MongoDB URI/server availability must be supplied on GB10. Local inference does
  not require that MongoDB use a cloud host; a local server is supported.
- Verify Python dependencies on Linux ARM64, particularly Rasterio/GDAL. This
  milestone introduces PyMongo, not another native GIS dependency.
- Run the app directly in a Python venv for this milestone. The existing sandbox
  deployment instructions do not copy the newly added Python modules.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Persistence tests use mongomock and cover reopening, changed-input history,
duplicate saves/tasks, status gates, invalid actions and interrupted-save recovery.
They are not proof of real MongoDB connectivity or ARM64 operation.

Implementation references: [PyMongo connection documentation](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/)
and [MongoDB atomicity boundaries](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
