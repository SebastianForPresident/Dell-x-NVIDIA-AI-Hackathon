"""React API backed exclusively by InvestigationService; no model inference."""

from datetime import date
import os
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError

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
def health(service=Depends(get_service)):
    return {"status": "ok", "database": "MongoDB via InvestigationService",
            "case_count": len(service.list_investigations()), "model_checked": False,
            "runtime": "OpenClaw integration pending; no inference enabled"}


@app.get("/api/cases")
def list_cases(service=Depends(get_service)):
    return [project(service, row["_id"]) for row in service.list_investigations()]


@app.post("/api/demo", status_code=201)
def create_demo(service=Depends(get_service)):
    return project(service, demo(service).investigation_id)


@app.post("/api/demo/reset", status_code=201)
def new_demo_run(service=Depends(get_service)):
    # A fresh run preserves the previous report, tasks, and audit history.
    return project(service, demo(service, fresh=True).investigation_id)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, service=Depends(get_service)):
    require_case(service, case_id)
    return project(service, case_id)


@app.post("/api/cases/{case_id}/demo-step")
def run_demo_step(case_id: str, service=Depends(get_service)):
    require_case(service, case_id)
    result = demo_step(service, case_id)
    if not result["ok"]:
        raise HTTPException(422, result["error"])
    return project(service, case_id)


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
    claim_id: str = Form(...), farm: str = Form(...), location: str = Form("Location not supplied"),
    cause: str = Form(...), crop: str = Form(...), loss_date: date = Form(...), acreage: int = Form(0),
    before_date: date = Form(...), after_date: date = Form(...), red_band: int = Form(1), nir_band: int = Form(2),
    weather_unit: str = Form("mm"), synthetic_demo: bool = Form(False), selected_field: int = Form(0),
    boundary: UploadFile = File(...), weather: UploadFile | None = File(None),
    crop_layer: UploadFile | None = File(None), before_image: UploadFile | None = File(None),
    after_image: UploadFile | None = File(None), claim_pdf: UploadFile | None = File(None),
    service=Depends(get_service),
):
    if not claim_id.strip() or not farm.strip() or acreage < 0 or before_date >= after_date:
        raise HTTPException(422, "Nonempty claim/farm, nonnegative acreage and ordered image dates required")
    bundle = uuid4().hex
    folder = asset_root() / bundle
    folder.mkdir()
    names = {}
    for key, upload, name in (("boundary", boundary, "boundary.geojson"), ("weather", weather, "weather.csv"),
                              ("crop", crop_layer, "crop.tif"), ("before", before_image, "before.tif"),
                              ("after", after_image, "after.tif")):
        names[key] = await save_upload(upload, folder, name, 256_000_000 if name.endswith(".tif") else 8_000_000)
    await save_upload(claim_pdf, folder, "claim.pdf", 20_000_000)
    assets = CaseAssets(folder, **names, before_date=before_date.isoformat(), after_date=after_date.isoformat(),
                        red_band=red_band, nir_band=nir_band, selected_field=selected_field, weather_unit=weather_unit)
    fields, _ = assets.fields()
    uploads = (boundary, weather, crop_layer, before_image, after_image, claim_pdf)
    synthetic = synthetic_demo or any(u and "SYNTHETIC" in (u.filename or "").upper() for u in uploads)
    tools = AgentTools.start(service, {"claim_id": claim_id.strip(), "farm": farm.strip(), "location": location,
        "reported_cause": cause, "claimed_crop": crop, "reported_loss_date": loss_date.isoformat(),
        "field": field_names(fields)[selected_field], "acreage": acreage, "synthetic_demo": synthetic,
        "asset_bundle": bundle, "origin": "upload"}, assets, actor="demo")
    # Preserve explicit upload analysis as deterministic application behavior, not AI.
    errors = []
    for name in ("check_crop_classification", "check_rainfall", "check_vegetation_change", "compare_neighboring_fields"):
        result = tools.invoke(name, {}, f"upload:{name}")
        if not result["ok"]:
            errors.append(name)
    if not errors:
        tools.invoke("save_investigation_report", {}, "upload:report")
    package = service.load_package(tools.investigation_id)
    issues = errors + [e["finding"]["check"] for e in package["evidence"] if e["finding"]["status"] != "supported"]
    if issues:
        tools.invoke("create_follow_up_task", {"title": "Review incomplete or conflicting evidence",
                     "reason": "; ".join(issues)}, "upload:followup")
    else:
        tools.invoke("set_case_status", {"status": "READY_FOR_ADJUSTER_REVIEW",
                     "reason": "Deterministic upload checks completed; human review required"}, "upload:ready")
    return project(service, tools.investigation_id)


STATIC_DIR = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[1] / "frontend" / "dist"))
if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        return FileResponse(STATIC_DIR / "index.html")
