# FieldTrace — Crop Insurance Forensics

FieldTrace prepares source-backed crop-loss evidence for a human insurance adjuster. The React website calls FastAPI, which uses one `InvestigationService` and a local MongoDB. Crop, rainfall, vegetation, and neighboring-field checks run against local files; their findings, actions, status changes, and report are saved together as an investigation. The app never approves or denies a claim.

The built-in DeWitt County, Illinois case is **synthetic**. Its weather, crop layer, imagery, farm, and field boundaries are fabricated for demonstration. They are not NOAA, USDA, or satellite observations.

## Start locally

Use Python 3.12+, Node 22.12+, and Docker with Compose. From the project root:

```bash
docker compose up -d mongo
export MONGODB_URI='mongodb://127.0.0.1:27017'
export MONGODB_DATABASE='crop_forensics'
export CROP_ASSET_DIR='./data/case_assets'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. For frontend development, run `npm --prefix frontend run dev` in another terminal and open **http://127.0.0.1:5173**. Vite proxies `/api` to FastAPI. The `.env.example` file lists settings but is not loaded automatically.

## Demo path

Open **Home → Dashboard → DeWitt demo claim**. Click **Run investigation** to run four real deterministic evidence checks, save the report, and mark the package ready for adjuster review. Each step is stored in MongoDB and displayed on the claim page. **Run fresh investigation** creates a new run while preserving the earlier one. The Dashboard shows saved actions, not simulated live telemetry.

Once a measured report exists, **Run local Qwen review** sends the structured claim, weather, NDVI, and measured findings to the fixed OpenShell route `https://inference.local/v1/chat/completions`. If the route is available, five short interpretations are saved with the same investigation and included in the downloadable Markdown report. If it is unavailable, the measured evidence and report still work. Qwen does not choose tool calls or decide the claim. This inference route has not been verified on the GB10 yet.

The import form accepts a GeoJSON field boundary and optional weather CSV, crop-layer GeoTIFF, before/after GeoTIFFs, and claim PDF. The current unified backend keeps a copy of uploaded assets under `CROP_ASSET_DIR` so an investigation can be reopened and its tools can read the same files. This directory is excluded from Git. A complete synthetic upload package can be generated with `.venv/bin/python scripts/generate_sample_case.py`.

## Input contract

| Input | Expected format |
| --- | --- |
| Boundary | GeoJSON Polygon/MultiPolygon or FeatureCollection, EPSG:4326. The first feature is the claimed field; other features are comparison fields. |
| Weather | CSV with `date,precipitation,normal_precipitation`, ISO dates, and consistent mm/inches units. Without supplied normals, a deficit/excess conclusion remains inconclusive. |
| Crop layer | Georeferenced USDA CDL GeoTIFF for the relevant year when using real evidence. |
| Imagery | Comparable georeferenced GeoTIFFs with red and NIR bands, dates, and already-masked cloud/invalid pixels. |
| Claim | Optional PDF; it is retained with the uploaded asset bundle, but the current investigation does not parse it automatically. |

Findings are **supported**, **contradicted**, **inconclusive**, or **unavailable** and retain measured values and source names. Screening thresholds are hackathon heuristics, not insurance standards: drought rainfall ≤60% of supplied normal, flood rainfall ≥150%, and NDVI decline ≤−0.12. Rainfall does not prove inundation; vegetation decline does not prove a cause.

## Runtime and tests

The active API uses `InvestigationService` for all investigation records. `agent_tools.py` exposes bounded tool schemas for a future OpenClaw adapter; autonomous tool selection is not connected to the website yet. See [ASSEMBLY.md](ASSEMBLY.md) for API and asset details and [AGENT_TOOLS.md](AGENT_TOOLS.md) for tool schemas. The optional Qwen review currently uses the OpenShell route described above; the Docker image includes its Python client, but GB10 networking and model availability still need hardware validation.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
npm --prefix frontend run build
```

The tests cover deterministic GIS behavior, MongoDB-backed investigation workflow with a mock database, the API demo and upload path, Qwen response validation and persistence, and the React production build. Two historical Streamlit tests are skipped because that UI was replaced. Live MongoDB connectivity and the complete demo path were also checked locally; OpenShell inference and ARM64 deployment remain unverified.
