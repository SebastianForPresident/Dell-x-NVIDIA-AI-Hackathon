# Crop Insurance Forensics

A local evidence assistant for crop-insurance adjusters. It reads a claim's field boundary, weather history, crop layer, and before/after imagery, then produces an auditable evidence package. It never approves or denies a claim.

## Run locally

Requires Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Open the local URL Streamlit prints. Choose **Synthetic demo** for a zero-file walkthrough, or **Upload case files** to analyze your own data. To generate a complete, clearly labeled synthetic upload folder:

Streamlit is the website frontend: the Python process serves a browser UI at `http://127.0.0.1:8501`. Leave the terminal running while using the site; `Ctrl+C` stops it. React is optional and is not needed for the hackathon demo.

```bash
.venv/bin/python scripts/generate_sample_case.py
```

Use `sample_case/` files with loss date **2026-07-18**, crop **Corn**, before date **2026-05-30**, after date **2026-08-12**, red band **1**, NIR band **2**. The sample data are fabricated and must not be presented as observations from NOAA, USDA, or a satellite.

## Input contract

| Input | Format | Use |
| --- | --- | --- |
| Claim | PDF, optional | Extract selectable text for manual verification of case fields. Scanned PDFs need OCR first. |
| Field boundary | GeoJSON Polygon/MultiPolygon or FeatureCollection in EPSG:4326 | Select one claimed field; other supplied polygons are compared as other fields. |
| Weather | CSV with `date,precipitation,normal_precipitation` | Dates are ISO `YYYY-MM-DD`; daily precipitation and matched normal use the selected mm/inches unit. `normal_precipitation` may be omitted, but deficit/excess will then be inconclusive. |
| Crop layer | USDA CDL GeoTIFF | Dominant CDL pixel class within the field. Use a layer for the claim year. |
| Before/after imagery | Two georeferenced GeoTIFFs | Mean NDVI from the selected red and NIR bands, sampled inside each polygon. Supply image dates in the UI. Both images should be comparable surface reflectance products with cloud/invalid pixels masked. |

The report records every finding's status, source, and measured values. Missing inputs remain **unavailable**; insufficient or unbracketed evidence remains **inconclusive**. The 30-day weather window needs at least 80% daily coverage. Screening thresholds are **demo heuristics**, not underwriting or meteorological standards: drought rainfall ≤60% of supplied normal, flood rainfall ≥150%, and NDVI decline ≤−0.12. A flood rainfall check does not establish inundation, and NDVI decline does not establish a cause. The app does not validate whether a CSV is truly from NOAA or a crop layer is truly from USDA.

## Dell Pro Max with GB10 / OpenShell

The deterministic GIS calculations run without a model. The claim-field suggestion and narrative buttons call only `https://inference.local/v1/chat/completions`, which must be routed by OpenShell to a model running on the same GB10. Claim-field extraction sends selectable PDF text to that local endpoint; the narrative sends only structured evidence. Model suggestions and wording are not the source of record. There are no cloud LLM calls in the runtime code.

Prepare [OpenShell](https://docs.nvidia.com/openshell/get-started/quickstart) and Ollama on the GB10 while network access is available. NVIDIA's [host Ollama tutorial](https://docs.nvidia.com/openshell/get-started/tutorials/inference-ollama) documents routing `inference.local` to Ollama. Use a local Qwen tag without `:cloud`; `qwen3.5` is the suggested demo model, while `qwen3.5:0.8b` is a smaller smoke-test option. On the GB10 host, start Ollama and configure the route:

```bash
ollama pull qwen3.5
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

In another host terminal, after the OpenShell gateway is running:

```bash
openshell provider create --name ollama --type openai --credential OPENAI_API_KEY=empty --config OPENAI_BASE_URL=http://host.openshell.internal:11434/v1
openshell inference set --provider ollama --model qwen3.5
openshell inference get
```

The `Dockerfile` builds the Python dependencies into an OpenShell base image on the GB10. This needs network during image build, but the resulting case investigation uses local files and local inference. From the repo directory on the GB10:

```bash
openshell sandbox create --from . --name crop-forensics --detach
openshell sandbox upload crop-forensics app.py /sandbox/app.py
openshell sandbox upload crop-forensics forensics.py /sandbox/forensics.py
openshell sandbox upload crop-forensics local_narrative.py /sandbox/local_narrative.py
openshell sandbox upload crop-forensics visuals.py /sandbox/visuals.py
openshell sandbox exec -n crop-forensics -- mkdir -p /sandbox/.streamlit
openshell sandbox upload crop-forensics .streamlit/config.toml /sandbox/.streamlit/config.toml
openshell sandbox exec -n crop-forensics -- mkdir -p /sandbox/scripts
openshell sandbox upload crop-forensics scripts/gb10_preflight.py /sandbox/scripts/gb10_preflight.py
openshell sandbox exec -n crop-forensics --workdir /sandbox -- python3 scripts/gb10_preflight.py
openshell sandbox exec -n crop-forensics --workdir /sandbox -- python3 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Run the final command in one terminal, then from another terminal use `openshell forward start 8501 crop-forensics` and open the printed URL. Click **Test local model route** in the sidebar before demonstrating PDF extraction or narrative drafting. [OpenShell's sandbox docs](https://docs.nvidia.com/openshell/sandboxes/manage-sandboxes) document image creation, upload, exec, and port forwarding. OpenShell and Ollama are not installed in this development environment, so the GB10 path still needs on-device verification.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests exercise weather coverage and cause-specific thresholds, CSV unit conversion, raster field sampling, CDL classification, and image-date handling. The generated synthetic upload folder has also been processed end-to-end through the evidence functions.

## Next steps for a production pilot

Add cloud/shadow masks and image quality metrics, field-level crop rotation checks, authoritative weather station metadata and normals, flood-specific surface-water evidence, input hashes, and human review controls before operational use. Those are outside this hackathon MVP.
