"""React API backed by InvestigationService and local OpenClaw/Ollama."""

import asyncio
import json
from datetime import date
import os
from pathlib import Path
from uuid import uuid4
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError

from agent_assets import CaseAssets
from agent_tools import AgentTools
from forensics import field_names, markdown_report
from runtime.run import run as run_agent
from runtime.live import read_snapshot
from server.database import get_service
from server.intake import LOCAL_FIELDS, create_claim
from server.integration import asset_root, demo, demo_step, project


app = FastAPI(title="Crop Insurance Forensics")


@app.exception_handler(PyMongoError)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "MongoDB unavailable; check canonical MONGODB configuration."})


@app.exception_handler(ValueError)
async def input_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc).replace(str(asset_root()), "<case-assets>")})


def require_case(service, case_id):
    try:
        return service.load_package(case_id)
    except ValueError as exc:
        raise HTTPException(404, "Investigation not found") from exc


@app.get("/api/health")
def health(service=Depends(get_service)):
    return {"status": "ok", "database": "MongoDB via InvestigationService",
            "case_count": len(service.list_investigations()), "model_checked": False,
            "runtime": "OpenClaw → local Ollama → gpt-oss:20b"}


@app.get("/api/cases")
def list_cases(service=Depends(get_service)):
    return [project(service, row["_id"]) for row in service.list_investigations()]


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    farm: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=10, max_length=2000)
    field_id: Literal["dewitt-public-2025", "dewitt-demo-field", "unregistered"]
    cause: Literal["Drought", "Flood", "Other"]
    crop: Literal["Corn", "Soybeans", "Winter wheat", "Other"]
    loss_date: date
    claim_id: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)


@app.get("/api/local-fields")
def local_fields():
    return LOCAL_FIELDS


@app.post("/api/claims", status_code=201)
def intake_claim(body: ClaimRequest, service=Depends(get_service)):
    return project(service, create_claim(service, body))


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
def get_markdown_report(case_id: str, service=Depends(get_service)):
    package = require_case(service, case_id)
    if package["report"] is None:
        raise HTTPException(409, "A final report has not been saved yet")
    content = markdown_report(package["report"])
    return PlainTextResponse(content, media_type="text/markdown")


@app.get("/api/cases/{case_id}/agent-stream")
async def agent_stream(case_id: str, request: Request, service=Depends(get_service)):
    require_case(service, case_id)
    async def events():
        previous = None
        while not await request.is_disconnected():
            snapshot = json.dumps(read_snapshot(case_id))
            if snapshot != previous:
                yield f"data: {snapshot}\n\n"
                previous = snapshot
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.04)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/cases/{case_id}/investigate")
def investigate_case(case_id: str, service=Depends(get_service)):
    require_case(service, case_id)
    try:
        run_agent(case_id)
    except RuntimeError as exc:
        raise HTTPException(503, "Local agent failed; inspect .runtime logs") from exc
    return project(service, case_id)


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: str = Field(min_length=1, max_length=1000)


@app.post("/api/cases/{case_id}/tasks", status_code=201)
def create_task(case_id: str, body: TaskRequest, service=Depends(get_service)):
    require_case(service, case_id)
    service.create_follow_up_task(case_id, body.title, body.reason, actor="human")
    return project(service, case_id)


@app.post("/api/cases/{case_id}/tasks/{task_id}/resolve")
def resolve_task(case_id: str, task_id: str, body: ResolutionRequest, service=Depends(get_service)):
    package = require_case(service, case_id)
    if not any(task["_id"] == task_id for task in package["tasks"]):
        raise HTTPException(404, "Follow-up task not found in this investigation")
    service.resolve_follow_up_task(case_id, task_id, body.resolution)
    return project(service, case_id)


async def save_upload(upload, folder, filename, limit):
    if upload is None:
        return None
    path = folder / filename  # Fixed application filename, never user-provided path.
    size = 0
    with path.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, "Evidence file exceeds upload limit")
            output.write(chunk)
    return filename


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
