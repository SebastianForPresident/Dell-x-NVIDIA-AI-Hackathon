# FieldTrace — Crop Insurance Forensics

A local evidence assistant for crop insurance adjusters. The React demo has three screens: Home, Dashboard, and Claim investigation. FastAPI measures weather, crop, vegetation, and neighboring-field evidence and saves it in local MongoDB. On the Claim screen, Qwen receives the structured local case data through NVIDIA OpenShell and writes five short interpretations for an adjuster. The measured findings remain available if Qwen is offline. The system never approves or denies a claim.
The merged repository also contains an optional [investigation history module](PERSISTENCE.md) for follow-up tasks and audit records. The React app currently uses its own `server/database.py` case collection; that module is not connected to the website.

Every built-in case is **synthetic** and labeled as such. The demo weather, crop, imagery, farm names, and field polygons are fabricated; they are not NOAA, USDA, or satellite observations.

## Start the website on a development machine

Requirements: Python 3.12+, Node 20.19+ or 22.12+, Docker with Compose. MongoDB runs in a local Docker container; no Atlas account is used.

```bash
docker compose up -d mongo
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
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

## Dell Pro Max with GB10: OpenShell + local MongoDB + Qwen

The runtime architecture is:

```text
Browser → React served by FastAPI inside OpenShell → local MongoDB on GB10 host
                                                ↘ inference.local → Ollama/Qwen on GB10 host
```

Prepare the model, Docker images, and build dependencies while connected. Use a Qwen model **without** a `:cloud` suffix. The app itself calls only `https://inference.local/v1/chat/completions` for inference; OpenShell routes that to the host Ollama provider. The deterministic evidence tools still work when Qwen is unavailable. See NVIDIA's [OpenShell quickstart](https://docs.nvidia.com/openshell/get-started/quickstart), [local Ollama tutorial](https://docs.nvidia.com/openshell/get-started/tutorials/inference-ollama), and [native TCP policy guidance](https://docs.nvidia.com/openshell/sandboxes/policies).

On the GB10 host:

```bash
docker compose up -d mongo
ollama pull qwen3.5
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

If Ollama already runs as a service, use that service and ensure the OpenShell gateway can reach it. In another terminal, with an active OpenShell gateway:

```bash
openshell provider create --name ollama --type openai --credential OPENAI_API_KEY=empty --config OPENAI_BASE_URL=http://host.openshell.internal:11434/v1
openshell inference set --provider ollama --model qwen3.5
openshell inference get
openshell sandbox create --from . --policy ./openshell-policy.yaml --name crop-forensics --detach
openshell sandbox exec -n crop-forensics --workdir /app -- python3 scripts/gb10_preflight.py
openshell sandbox exec -n crop-forensics --workdir /app -- python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

The local `Dockerfile` builds React and Python dependencies into the OpenShell sandbox image. `openshell-policy.yaml` grants the Python process native TCP access **only** to `host.openshell.internal:27017` for MongoDB; `inference.local` is handled by OpenShell. Start the final API command in one terminal. In another terminal:

```bash
openshell forward start 8000 crop-forensics
```

Open the printed URL and use **System status → Test model route** before the Qwen demo. The OpenShell/GB10 sequence must be verified on the event hardware; OpenShell and Ollama are not installed in this development environment.

## Checks

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
cd frontend && npm run build
```

Tests cover weather coverage and cause-specific thresholds, CSV unit conversion, raster field sampling, CDL classification, image-date handling, synthetic seed integrity, investigation history, and the fixed OpenShell inference endpoint. The React production bundle is built locally.
