"""Local FastAPI backend: MongoDB records, forensic tools, and Qwen via OpenShell."""

from contextlib import asynccontextmanager
from datetime import date, datetime
import hashlib
import io
import os
from pathlib import Path
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader
from pymongo.errors import DuplicateKeyError, PyMongoError

from forensics import (
    Finding, build_report, crop_finding, field_names, load_boundary, markdown_report,
    ndvi_mean, neighbors_finding, parse_weather, vegetation_finding, weather_finding,
)
from local_narrative import analyze_structured_case, check_local_model, extract_claim_fields, write_narrative
from server.database import case_document, cases, client, initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield
    client.close()


app = FastAPI(title="Crop Insurance Forensics", lifespan=lifespan)


def _get_case(case_id: str) -> dict:
    doc = case_document(case_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return doc


async def _read_small(upload: UploadFile | None, limit: int = 8_000_000) -> bytes | None:
    if upload is None:
        return None
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"{upload.filename} exceeds the {limit // 1_000_000} MB limit")
    return content


async def _save_raster(upload: UploadFile | None, folder: Path, name: str) -> tuple[Path | None, str | None]:
    if upload is None:
        return None, None
    path = folder / name
    digest = hashlib.sha256()
    with path.open("wb") as output:
        while chunk := await upload.read(4 * 1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    return path, digest.hexdigest()


@app.get("/api/health")
def health():
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"Local MongoDB unavailable: {exc}") from exc
    return {"status": "ok", "database": "local MongoDB", "case_count": cases.count_documents({}),
            "model_route": "https://inference.local", "model_checked": False}


@app.get("/api/cases")
def list_cases():
    return list(cases.find({}, {"_id": 0, "claim_text": 0}).sort("created_at", -1))


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    doc = _get_case(case_id)
    doc.pop("claim_text", None)
    return doc


@app.get("/api/cases/{case_id}/report.md")
def get_markdown_report(case_id: str):
    doc = _get_case(case_id)
    report = markdown_report(doc["report"])
    if doc.get("ai_review"):
        report += "\n## Local Qwen interpretation — adjuster review required\n\n"
        for key, label in (("weather", "Weather"), ("vegetation", "Vegetation"),
                           ("crop", "Crop"), ("neighbors", "Neighbor fields"),
                           ("overall", "Overall evidence")):
            report += f"### {label}\n\n{doc['ai_review'][key]}\n\n"
    return PlainTextResponse(report, media_type="text/markdown")


@app.post("/api/runtime/check-model")
def check_model():
    try:
        response = check_local_model()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenShell/Qwen inference unavailable: {exc}") from exc
    return {"status": "ok", "route": "https://inference.local", "response": response}


@app.post("/api/cases/{case_id}/narrative")
def draft_narrative(case_id: str):
    doc = _get_case(case_id)
    try:
        narrative = write_narrative(doc["report"])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenShell/Qwen inference unavailable: {exc}") from exc
    cases.update_one({"id": case_id}, {"$set": {"narrative": narrative}})
    return {"narrative": narrative}


@app.post("/api/cases/{case_id}/ai-review")
def review_case_with_qwen(case_id: str):
    doc = _get_case(case_id)
    try:
        review = analyze_structured_case(doc)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenShell/Qwen review unavailable: {exc}") from exc
    cases.update_one({"id": case_id}, {"$set": {"ai_review": review}})
    return {"ai_review": review}


@app.post("/api/cases/{case_id}/claim-suggestions")
def claim_suggestions(case_id: str):
    doc = _get_case(case_id)
    if not doc.get("claim_text"):
        raise HTTPException(status_code=400, detail="This case has no selectable claim PDF text")
    try:
        return {"suggestions": extract_claim_fields(doc["claim_text"])}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenShell/Qwen inference unavailable: {exc}") from exc


@app.post("/api/cases/analyze", status_code=201)
async def analyze_case(
    claim_id: str = Form(...),
    farm: str = Form(...),
    location: str = Form("Location not supplied"),
    cause: str = Form(...),
    crop: str = Form(...),
    loss_date: date = Form(...),
    acreage: int = Form(0),
    before_date: date = Form(...),
    after_date: date = Form(...),
    red_band: int = Form(1),
    nir_band: int = Form(2),
    weather_unit: str = Form("mm"),
    synthetic_demo: bool = Form(False),
    selected_field: int = Form(0),
    boundary: UploadFile = File(...),
    weather: UploadFile | None = File(None),
    crop_layer: UploadFile | None = File(None),
    before_image: UploadFile | None = File(None),
    after_image: UploadFile | None = File(None),
    claim_pdf: UploadFile | None = File(None),
):
    claim_id = claim_id.strip()
    if not claim_id or not farm.strip():
        raise HTTPException(status_code=422, detail="Claim ID and farm name are required")
    if cases.find_one({"id": claim_id}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Claim ID already exists")
    if red_band < 1 or nir_band < 1 or red_band == nir_band:
        raise HTTPException(status_code=422, detail="Red and NIR bands must be distinct positive indices")
    if weather_unit not in {"mm", "inches"}:
        raise HTTPException(status_code=422, detail="Weather unit must be mm or inches")
    if acreage < 0:
        raise HTTPException(status_code=422, detail="Acreage cannot be negative")
    if before_date >= after_date:
        raise HTTPException(status_code=422, detail="Before image date must precede after image date")

    try:
        boundary_bytes = await _read_small(boundary)
        features = load_boundary(boundary_bytes)
        if not 0 <= selected_field < len(features):
            raise ValueError("Selected field index is outside the GeoJSON feature list")
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    geometry = features[selected_field]["geometry"]
    finding_list: list[Finding] = []
    weather_series = []
    ndvi_series = []
    documents = [boundary.filename]
    file_hashes = {boundary.filename: hashlib.sha256(boundary_bytes).hexdigest()}
    claim_text = None

    if claim_pdf is not None:
        pdf_bytes = await _read_small(claim_pdf, 20_000_000)
        documents.append(claim_pdf.filename)
        file_hashes[claim_pdf.filename] = hashlib.sha256(pdf_bytes).hexdigest()
        try:
            claim_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)[:16000]
        except Exception:
            claim_text = None

    weather_bytes = await _read_small(weather)
    if weather_bytes is not None:
        documents.append(weather.filename)
        file_hashes[weather.filename] = hashlib.sha256(weather_bytes).hexdigest()
        try:
            weather_rows = parse_weather(weather_bytes, weather_unit)
            weather_series = [{"date": row["date"].isoformat(),
                               "rainfall": round(row["precipitation_mm"], 2),
                               "normal": round(row["normal_mm"], 2) if row["normal_mm"] is not None else None}
                              for row in weather_rows]
            finding_list.append(weather_finding(weather_rows, loss_date, cause=cause))
            finding_list[-1].source = weather.filename
        except ValueError as exc:
            finding_list.append(Finding("Precipitation", "unavailable", str(exc), weather.filename, {}))
    else:
        finding_list.append(Finding("Precipitation", "unavailable", "No weather CSV supplied.", "No source", {}))

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        crop_path, crop_hash = await _save_raster(crop_layer, folder, "crop.tif")
        before_path, before_hash = await _save_raster(before_image, folder, "before.tif")
        after_path, after_hash = await _save_raster(after_image, folder, "after.tif")
        for upload, digest in [(crop_layer, crop_hash), (before_image, before_hash), (after_image, after_hash)]:
            if upload is not None:
                documents.append(upload.filename)
                file_hashes[upload.filename] = digest

        if crop_path:
            try:
                finding_list.append(crop_finding(crop_path, geometry, crop))
                finding_list[-1].source = crop_layer.filename
            except Exception as exc:
                finding_list.append(Finding("Crop type", "unavailable", str(exc), crop_layer.filename, {}))
        else:
            finding_list.append(Finding("Crop type", "unavailable", "No crop layer supplied.", "No source", {}))

        neighbor_changes = []
        if before_path and after_path:
            try:
                before = ndvi_mean(before_path, geometry, red_band, nir_band)
                after = ndvi_mean(after_path, geometry, red_band, nir_band)
                finding_list.append(vegetation_finding(before, after, before_date, after_date,
                                                       loss_date, f"{before_image.filename}; {after_image.filename}"))
                if before is not None and after is not None:
                    ndvi_series = [{"date": before_date.isoformat(), "ndvi": round(before, 3)},
                                   {"date": after_date.isoformat(), "ndvi": round(after, 3)}]
                for index, feature in enumerate(features):
                    if index == selected_field:
                        continue
                    try:
                        prior = ndvi_mean(before_path, feature["geometry"], red_band, nir_band)
                        later = ndvi_mean(after_path, feature["geometry"], red_band, nir_band)
                        if prior is not None and later is not None:
                            neighbor_changes.append(later - prior)
                    except ValueError:
                        continue
            except Exception as exc:
                finding_list.append(Finding("Vegetation change", "unavailable", str(exc),
                                            f"{before_image.filename}; {after_image.filename}", {}))
        else:
            finding_list.append(Finding("Vegetation change", "unavailable",
                                        "Both before and after imagery are required.", "No valid image pair", {}))
        finding_list.append(neighbors_finding(neighbor_changes))

    is_synthetic = synthetic_demo or any("SYNTHETIC" in name.upper() for name in documents)
    report = build_report(claim_id, cause, loss_date, field_names(features)[selected_field], finding_list,
                          demo=is_synthetic)
    counts = report["evidence_summary"]
    status = "Evidence ready" if counts["inconclusive"] == counts["unavailable"] == 0 else "Needs review"
    doc = {
        "id": claim_id, "farm": farm.strip(), "location": location.strip(), "crop": crop,
        "cause": cause, "loss_date": loss_date.isoformat(), "acreage": acreage,
        "created_at": datetime.now().date().isoformat(), "status": status,
        "synthetic_demo": is_synthetic, "origin": "upload", "boundary": {"type": "FeatureCollection", "features": features},
        "selected_field": selected_field, "weather_series": weather_series, "ndvi_series": ndvi_series,
        "report": report, "narrative": None, "documents": documents,
        "file_hashes": file_hashes, "claim_text": claim_text,
        "workflow": [
            {"stage": "Claim intake", "detail": "Claim fields recorded", "state": "complete"},
            {"stage": "Weather review", "detail": "Precipitation evidence evaluated", "state": "complete"},
            {"stage": "Crop verification", "detail": "Crop layer evaluated", "state": "complete"},
            {"stage": "Imagery comparison", "detail": "Field and supplied comparison polygons evaluated", "state": "complete"},
            {"stage": "Evidence package", "detail": "Structured report saved to local MongoDB", "state": "complete"},
        ],
    }
    try:
        cases.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Claim ID already exists") from exc
    doc.pop("_id", None)
    doc.pop("claim_text", None)
    return doc


STATIC_DIR = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[1] / "frontend" / "dist"))
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(STATIC_DIR / "index.html")
