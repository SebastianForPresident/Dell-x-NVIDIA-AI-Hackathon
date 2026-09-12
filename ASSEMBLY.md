# Unified application handoff

Starting HEAD was `785ce03` (the earlier tool work had already been committed by
the team). Integrated `c2a88d4` cleanup, then `d1e06b3` drought data by fast-forward.
No merge conflicts or local changes were discarded. This assembly is uncommitted.

## One authoritative state

`server.database.get_service()` constructs InvestigationService using the canonical
MongoStore configuration. `server.integration.project()` converts the service's
records into the existing React view shape without writing another copy. API
`id` is the investigation ID; `claim_id` is the human-readable claim identifier.
The existing `cases` collection is untouched and inactive, not automatically migrated.
There are no dual writes. Old service investigations remain readable; those without
retained assets show an explicit asset warning rather than invented imagery.

The six active collections remain claims, investigations, evidence, agent_actions,
follow_up_tasks and reports. Report previews are generated from current findings;
`report_saved` distinguishes previews from persisted final reports. Raw action
records and transitions are available in the React audit details.

## API

| Method / path | Behavior |
| --- | --- |
| GET /api/health | Database/service readiness; explicitly says inference is pending |
| GET /api/cases | Investigation projections; no implicit database seeding |
| POST /api/demo | Idempotently create/load the synthetic DeWitt investigation |
| POST /api/demo/reset | Create a fresh run while preserving all prior history |
| GET /api/cases/{investigation_id} | Metadata, status, evidence, actions, tasks, transitions, report, charts |
| POST /api/cases/{investigation_id}/demo-step | Execute one deterministic demo step through preserved tools |
| GET /api/cases/{investigation_id}/report.md | Saved report; 409 until a final report exists |
| POST /api/cases/analyze | Existing multipart form, durable asset intake, deterministic tool analysis |
| POST /api/cases/{id}/tasks | Human task, JSON `{title, reason}` |
| POST /api/cases/{id}/tasks/{task_id}/resolve | Human resolution, JSON `{resolution}` |

No approve/deny/payout endpoints or old model/narrative endpoints exist. React polls
the same projection every five seconds. The original field sketch, charts, evidence
cards, report layout, and navigation are retained. New UI controls are limited to
loading/running the demo, viewing workflow/audit state, and resolving tasks.

## Demo / future model binding

Generated DeWitt assets are small synthetic corn rasters, before/after red/NIR
imagery, boundaries, and 30 daily weather rows. They produce a 30 mm rainfall total
against 90 mm normal and substantial NDVI decline. All are explicitly synthetic.
The teammate's 2025 county drought CSV is preserved, but does not replace these
2026 daily weather inputs. County drought categories are not daily rainfall data.

The manual demo driver has a fixed sequence, no model client and no autonomous
decision-making. Demo/upload tool calls are truthfully attributed `actor=demo`;
future OpenClaw calls default to `actor=agent`. Both use the same validation and
readiness safeguards. A successful demo ends READY_FOR_ADJUSTER_REVIEW. Errors,
missing or conflicting evidence remain visible and require follow-up.

For the runtime integrator:

```python
from server.database import get_service
from server.integration import bound_tools

tools = bound_tools(get_service(), investigation_id)  # actor=agent by default
schemas = tools.schemas()
result = tools.invoke(tool_name, validated_arguments, runtime_call_id)
```

Verify OpenClaw 2026.9.4's registration API on GB10, map it to these callbacks,
verify local Ollama gpt-oss:20b tool calling, and pass results back to the model.
No provider-specific API has been invented. React needs no provider knowledge.

## Configuration / retained files

- MONGODB_URI and MONGODB_DATABASE are the only active MongoDB environment names.
- CROP_ASSET_DIR defaults to data/case_assets. Retain it alongside MongoDB storage.
- Fixed generated filenames keep model/user paths out of filesystem operations.
- Uploaded fields/dates/bands are validated; uploaded file content is hash-bound
  to the investigation. Changed files require a new investigation.
- Uploads create a new snapshot/bundle per submission. Failed uploads may leave
  orphan directories; no destructive cleanup is performed.
- One writer per investigation remains the supported mode. Cross-collection
  operations are retryable but not transactional. No queues/auth were added.
- The projection currently hashes/reads registered assets; keep demo inputs small
  and clipped. Large rasters and many concurrent cases need later optimization.

## Legacy / GB10 limits

Active API, frontend and Dockerfile no longer use OpenShell, Qwen or inference.local.
Historical files remain outside the active import/build path. No live inference ran.
Docker now uses Python 3.12 and the React build, with runtime-provided MongoDB URI.
ARM64 image pulls and Rasterio/GDAL wheel compatibility are unverified here.

Tests use FastAPI TestClient, mongomock and real Rasterio calculations. They exercise
API -> service -> tools -> evidence/audit/report, retained uploads, human task
resolution, API visibility after reopening, and absence of insurance-decision APIs.
They do not prove live MongoDB or GB10 integration. No frontend test runner/typecheck
script exists; the Vite production build is the frontend verification.
