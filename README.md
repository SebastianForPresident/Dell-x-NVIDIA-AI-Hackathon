# FieldTrace — Crop Insurance Forensics

A local evidence assistant for crop insurance adjusters. The React demo has three screens: Home, Dashboard, and Claim investigation. FastAPI measures weather, crop, vegetation, and neighboring-field evidence and saves it in local MongoDB. On the Claim screen, Qwen receives the structured local case data through NVIDIA OpenShell and writes five short interpretations for an adjuster. The measured findings remain available if Qwen is offline. The system never approves or denies a claim.
The merged repository also contains an optional [investigation history module](PERSISTENCE.md) for follow-up tasks and audit records. The React app currently uses its own `server/database.py` case collection; that module is not connected to the website.

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

Open **http://127.0.0.1:8000**. The API seeds four synthetic case records into an empty MongoDB collection. It also adds the featured `CLM-2841` walkthrough to an existing collection if missing, without replacing saved cases. The website reads records from the API; there is no hard-coded frontend fallback. For frontend development, run `cd frontend && npm run dev` in a second terminal and open **http://127.0.0.1:5173**; Vite proxies `/api` to FastAPI.

For the demo, open **Home → Dashboard → CLM-2841**. The saved synthetic evidence is ready to inspect immediately. Click **Run local Qwen review** on the claim page when the OpenShell model route is connected; the model's response is stored with the case and appears alongside the four measured findings. The progress display distinguishes saved measurements from the actual Qwen request. The dashboard shows saved workflow stages, not simulated live agent events. On a development machine without OpenShell, the Qwen request shows an unavailable message while the evidence report still works.

The new-investigation form accepts a GeoJSON field boundary and optional weather CSV, crop layer, before/after rasters, and PDF. It saves the report, chart data, source file names, and SHA-256 hashes to MongoDB. Raw GeoTIFFs are processed from temporary files and discarded. PDF text is retained locally for optional Qwen field suggestions; the raw PDF is not retained.

To generate a complete synthetic upload package:

```bash
.venv/bin/python scripts/generate_sample_case.py
```

Use `sample_case/` files with loss date **2026-07-18**, crop **Corn**, before date **2026-05-30**, after date **2026-08-12**, red band **1**, and NIR band **2**.

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
