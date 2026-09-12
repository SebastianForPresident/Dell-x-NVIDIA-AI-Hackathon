# FieldTrace — Crop Insurance Forensics

FieldTrace is a local evidence assistant for crop-insurance adjusters. It resolves a fictional carrier policy and insured field from a local registry, evaluates locally cached public weather, crop, and satellite evidence against the insured geometry, and prepares a reviewable report. The adjuster makes the insurance decision.

The claim statement is a hypothesis. Reported crop, cause, and narrative never select the field or its evidence. The carrier registry supplies field identity and geometry; USDA Cropland Data Layer classifications are evidence about what was observed inside that boundary.

## Data model

`data/carrier_registry/insured_fields.json` contains fictional carrier and policy records. `FIELD-17` is the fictional Prairie View Farms North 40 policy in DeWitt County, Illinois. Its evidence package uses cached real public data from NOAA NCEI, USDA NASS CDL, and Copernicus Sentinel-2. `FIELD-KS-04` is a second fictional carrier field with distinct Kansas geometry and intentionally unavailable local public evidence.

The normal intake flow is **insured farm → insured field → claim story**. Two claims against `FIELD-17` always receive the same carrier geometry and evidence, even when one reports corn/drought and another reports soybeans/flooding. The findings can therefore support one story and contradict the other. Selecting `FIELD-KS-04` produces its own geometry and unavailable findings followed by a request for evidence; it never borrows DeWitt measurements.

Synthetic fixtures remain available only as clearly labeled regression/demo history. Carrier records are fictional. Public evidence provenance is stored with each evidence package.

## Start locally

Ollama and MongoDB must be running. On the configured GB10 machine, run:

```bash
./scripts/start_demo.sh
```

Open **http://127.0.0.1:8000**. The launcher reuses a healthy server already listening on port 8000 instead of trying to bind a second copy.

For a fresh checkout, install and build first:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix frontend
npm run build --prefix frontend
docker compose up -d mongo
./scripts/start_demo.sh
```

For frontend development, run `npm run dev --prefix frontend` and open **http://127.0.0.1:5173**. Vite proxies `/api` to FastAPI.

## Judge demo

Create a claim, select **Prairie View Farms → North 40**, choose July 18, 2026, and report corn damaged by drought. Run the investigation to show the local agent selecting registered tools and producing measured evidence. Then create a second claim for the same field that reports soybeans and flooding: geometry and measured values remain identical while crop and rainfall findings contradict the story. A claim on **High Plains Demo Farm → South Quarter** shows a different insured geometry and an honest `NEEDS_EVIDENCE` result.

The active runtime path is:

```text
React → FastAPI → OpenClaw → local Ollama → gpt-oss:20b
      → registered validated tools → InvestigationService → MongoDB → React
```

OpenClaw receives eight bounded application tools. The model chooses tool calls; there is no fixed four-call script in the normal browser flow. The configured provider is local Ollama with no fallback. The investigation path does not use OpenAI, Qwen, OpenShell, cloud inference, or runtime data downloads. `scripts/cache_real_demo.py` is a separate administrative ingestion utility and may access public sources when explicitly run; investigations read only the cached files.

## Evidence contract

| Input | Role |
| --- | --- |
| Carrier field geometry | Authoritative insured-field identity, GeoJSON EPSG:4326 |
| Weather | Cached CSV with precipitation and normal precipitation |
| Crop layer | Cached georeferenced USDA CDL GeoTIFF |
| Imagery | Cached comparable red/NIR GeoTIFFs with acquisition dates |
| Claim statement | Reported crop, cause, date, and narrative to test against evidence |

Findings are `supported`, `contradicted`, `inconclusive`, or `unavailable` and retain measured values and source provenance. Screening thresholds are hackathon heuristics rather than insurance standards: drought rainfall ≤60% of supplied normal, flood rainfall ≥150%, and NDVI decline ≤−0.12. Rainfall does not prove inundation, and vegetation decline does not prove a cause.

## Validation

```bash
.venv/bin/python -m unittest discover -s tests -v
npm run build --prefix frontend
```

The tests cover registry resolution, hypothesis-independent evidence binding, distinct missing-evidence fields, deterministic GIS calculations, offline evidence access, MongoDB persistence, OpenClaw runtime validation, API behavior, and the React production build. Runtime receipts and browser artifacts are preserved separately; see [RUNTIME.md](RUNTIME.md) and `docs/GB10_RUNTIME_PROOF.json`.
