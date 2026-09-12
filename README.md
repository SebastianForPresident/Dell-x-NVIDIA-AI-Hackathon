# Fieldnote ? Crop Insurance Forensics

AI does the detective work; the human adjuster makes the decision.

React ? FastAPI ? InvestigationService ? MongoDB is now one application. The
same investigation records are used by the validated agent tools. No active
endpoint uses the old `cases` collection or performs model inference.

## Start locally / on GB10

Use Python 3.12, Node 22.12+ and a reachable MongoDB server. For the provided local
Mongo container, run `docker compose up -d mongo`. Then:

```bash
export MONGODB_URI='mongodb://127.0.0.1:27017'
export MONGODB_DATABASE='crop_forensics'
export CROP_ASSET_DIR='./data/case_assets'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci --no-audit --no-fund
npm run build
cd ..
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Environment variables must be exported; `.env` is not
loaded automatically. On PowerShell use `$env:MONGODB_URI = 'mongodb://127.0.0.1:27017'`
and corresponding assignments for the other two variables; Python is
`.venv\Scripts\python.exe`.

For frontend development, `npm run dev` in `frontend/` starts Vite with an API
proxy to port 8000. The Dockerfile also builds this lower stack without OpenShell;
provide MONGODB_URI at runtime and mount `/data/case_assets` for durable uploads.
Docker/ARM64 execution remains to be verified on GB10.

## Demo

The empty workspace loads one **clearly synthetic DeWitt County, Illinois corn
and drought claim**. Otherwise click **Load DeWitt demo**. The demo starts NEW.
Click **Run deterministic demo checks** to see actual GIS tool results, audit
records, saved report, and READY_FOR_ADJUSTER_REVIEW. These calls have `actor=demo`.
This is a scripted lower-stack demonstration, not autonomous AI inference.

React polls every five seconds, so later OpenClaw tool calls against the same
investigation will update the view without a second persistence model.
Follow-up tasks and human resolution notes are visible. A final report is
exportable only after it is saved. Readiness never approves or denies a claim.

The upload form retains approved GeoJSON/CSV/GeoTIFF/PDF files under CROP_ASSET_DIR
and performs explicit deterministic analysis through the same tools. Evidence,
actions, reports, and tasks are stored by InvestigationService. Upload failures
can leave orphan asset directories; this milestone does not delete or garbage
collect evidence. No PDF extraction/inference runs in this milestone.

All generated demo assets are fabricated, not NOAA, USDA, or satellite observations.
The supplied `data/drought_20250101_20251231.csv` is preserved as 2025 county drought
context; it is not used as daily rainfall/normal evidence for the 2026 synthetic
scenario. No nationwide datasets are downloaded.

## Input contract and interpretation

| Input | Expected format |
| --- | --- |
| Boundary | GeoJSON Polygon/MultiPolygon or FeatureCollection, EPSG:4326. The first feature is the claimed field in the upload form; other features are comparison fields. |
| Weather | CSV with `date,precipitation,normal_precipitation`; ISO dates, daily values, and consistent mm/inches units. `normal_precipitation` may be omitted, but a deficit/excess conclusion then stays inconclusive. |
| Crop layer | Georeferenced USDA CDL GeoTIFF, ideally for the claim year. |
| Before/after imagery | Comparable georeferenced GeoTIFFs with red and NIR bands. Set their dates and band numbers in the form. Cloud and invalid pixels should already be masked. |
| Claim | Optional selectable-text PDF. Scanned PDFs need OCR before field suggestions can work. |

The report marks each check **supported**, **contradicted**, **inconclusive**, or **unavailable** and retains measured values and source names. The 30-day weather window needs at least 80% daily coverage. Screening thresholds are hackathon heuristics, not insurance standards: drought rainfall ≤60% of supplied normal, flood rainfall ≥150%, and NDVI decline ≤−0.12. Rainfall does not prove inundation, and vegetation decline does not prove a cause. No claim decision is made.

## Runtime integration next

OpenClaw 2026.9.4 ? local Ollama ? gpt-oss:20b is the intended inference path.
Registration and local tool calling must be verified on GB10. Bind the selected
investigation with `server.integration.bound_tools(service, investigation_id)`;
use its `schemas()` and `invoke()` methods from the verified OpenClaw adapter.
There is no cloud fallback or alternate autonomous runtime.

Legacy `local_narrative.py`, `openshell-policy.yaml`, and `scripts/gb10_preflight.py`
remain historical files. They are not imported by the active API or copied into
the new Docker runtime. The old NY `server/seed.py` is also inactive.

See [ASSEMBLY.md](ASSEMBLY.md) for endpoints, integration details, and limits;
[AGENT_TOOLS.md](AGENT_TOOLS.md) documents the preserved tool schemas.

## Test

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Tests use real deterministic GIS calculations on synthetic assets and mocked
MongoDB. Live MongoDB, Docker/ARM64 and OpenClaw inference need GB10 validation.
