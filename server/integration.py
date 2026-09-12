"""Read projections and trusted case binding shared by API and future runtime."""

from datetime import date
import os
from pathlib import Path
import math
from uuid import uuid4

from agent_assets import CaseAssets
from agent_tools import AgentTools
from forensics import Finding, build_report, parse_weather
from server.demo_assets import create_demo_assets


def asset_root():
    root = Path(os.environ.get("CROP_ASSET_DIR", "data/case_assets")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def demo(service, fresh=False):
    if not fresh:
        for row in service.list_investigations():
            if row["metadata"].get("origin") == "demo" and row["metadata"].get("asset_bundle") == "dewitt-synthetic-v1":
                return bound_tools(service, row["_id"], actor="demo")
    bundle = "dewitt-synthetic-v1"
    assets = create_demo_assets(asset_root() / bundle)
    metadata = {"claim_id": "DEWITT-2026-DEMO", "reported_cause": "Drought", "reported_loss_date": "2026-07-18",
                "field": "Synthetic corn field", "claimed_crop": "Corn", "synthetic_demo": True,
                "farm": "DeWitt Demonstration Farm", "location": "DeWitt County, Illinois", "acreage": 184,
                "asset_bundle": bundle, "origin": "demo"}
    if fresh:
        metadata["demo_run"] = uuid4().hex
    return AgentTools.start(service, metadata, assets, actor="demo")


def bound_tools(service, investigation_id, actor="agent"):
    record = service.load_package(investigation_id)["investigation"]
    root = asset_root()
    bundle = record["metadata"].get("asset_bundle")
    if not bundle:
        raise ValueError("This historical investigation has no retained asset bundle.")
    folder = (root / bundle).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Invalid asset bundle.")
    manifest = record["context"]["agent_asset_manifest"]
    paths = {key: manifest[key]["name"] if manifest[key] else None
             for key in ("boundary", "weather", "crop", "before", "after")}
    options = {key: manifest[key] for key in
               ("before_date", "after_date", "selected_field", "red_band", "nir_band", "weather_unit")}
    options["provenance"] = manifest.get("provenance")
    return AgentTools(service, investigation_id, CaseAssets(folder, **paths, **options), actor=actor)


def project(service, investigation_id):
    """Compatibility API shape; no parallel cases collection."""
    package = service.load_package(investigation_id)
    record, report = package["investigation"], package["report"]
    meta = record["metadata"]
    findings = [e["finding"] for e in package["evidence"]]
    preview = report or build_report(record["claim_id"], meta["reported_cause"],
        date.fromisoformat(meta["reported_loss_date"]), meta["field"], [Finding(**f) for f in findings],
        demo=meta.get("synthetic_demo", False))
    boundary = {"type": "FeatureCollection", "features": record["context"].get("features", [])}
    weather, documents = [], []
    asset_error = None
    try:
        tools = bound_tools(service, investigation_id)
        fields, _ = tools.assets.fields()
        boundary["features"] = fields
        documents = [v["name"] for v in tools.manifest.values() if isinstance(v, dict) and "name" in v]
        if tools.assets.weather:
            weather = [{"date": r["date"].isoformat(), "rainfall": r["precipitation_mm"], "normal": r["normal_mm"]}
                       for r in parse_weather(tools.assets.path("weather").read_bytes(), tools.assets.weather_unit)]
            if any(not math.isfinite(r["rainfall"]) or
                   (r["normal"] is not None and not math.isfinite(r["normal"])) for r in weather):
                weather = []
                raise ValueError("Weather contains non-finite measurements.")
    except (ValueError, OSError, KeyError) as exc:
        asset_error = str(exc).replace(str(asset_root()), "<case-assets>")
    vegetation = next((f["values"] for f in findings if f["check"] == "Vegetation change"), {})
    ndvi = [{"date": vegetation[f"{when}_date"], "ndvi": vegetation[f"{when}_ndvi"]}
            for when in ("before", "after") if f"{when}_ndvi" in vegetation]
    actions = package["actions"]
    workflow = [{"stage": a["tool"], "detail": f"{a['actor']}: " +
                ("Completed" if a["result"].get("ok", True) else str(a["result"].get("error"))),
                "state": "complete" if a["result"].get("ok", True) else "error"} for a in actions]
    return {"id": investigation_id, "claim_id": record["claim_id"], "investigation_id": investigation_id,
            "claim_description": meta.get("claim_description", ""),
            "field": meta["field"], "farm": meta.get("farm", meta["field"]), "location": meta.get("location", "Not supplied"),
            "crop": meta.get("claimed_crop", "Not supplied"), "cause": meta["reported_cause"],
            "loss_date": meta["reported_loss_date"], "acreage": meta.get("acreage", 0),
            "created_at": record["created_at"].date().isoformat(), "status": record["status"],
            "synthetic_demo": meta.get("synthetic_demo", False), "origin": meta.get("origin", "historical"),
            "boundary": boundary, "selected_field": record["context"].get("agent_asset_manifest", {}).get("selected_field", 0),
            "weather_series": weather, "ndvi_series": ndvi, "report": preview,
            "provenance": record["context"].get("agent_asset_manifest", {}).get("provenance"),
            "agent_run": next((a["result"] for a in reversed(actions) if a["tool"] == "openclaw_run"), None),
            "report_saved": report is not None, "documents": documents, "ai_review": record.get("ai_review"),
            "workflow": workflow, "actions": actions, "tasks": package["tasks"],
            "transitions": record["transitions"], "evidence": package["evidence"], "asset_error": asset_error}


def demo_step(service, investigation_id):
    """Explicit deterministic smoke/demo driver. Not an autonomous agent."""
    tools = bound_tools(service, investigation_id, actor="demo")
    package = service.load_package(investigation_id)
    if package["investigation"]["metadata"].get("origin") != "demo":
        raise ValueError("The scripted demo driver is restricted to demo investigations.")
    if package["investigation"]["status"] == "READY_FOR_ADJUSTER_REVIEW":
        return {"ok": True, "data": {"status": "READY_FOR_ADJUSTER_REVIEW"}}
    checked = {e["finding"]["check"] for e in package["evidence"]}
    for tool, label in (("check_crop_classification", "Crop type"), ("check_rainfall", "Precipitation"),
                        ("check_vegetation_change", "Vegetation change"), ("compare_neighboring_fields", "Other supplied fields")):
        if label not in checked:
            return tools.invoke(tool, {}, f"demo:{tool}")
    if not package["report"]:
        return tools.invoke("save_investigation_report", {}, "demo:report")
    bad = [e["finding"] for e in package["evidence"] if e["finding"]["status"] != "supported"]
    if bad:
        return tools.invoke("create_follow_up_task", {"title": "Review incomplete or conflicting evidence",
                            "reason": "; ".join(f["check"] for f in bad)}, "demo:followup")
    return tools.invoke("set_case_status", {"status": "READY_FOR_ADJUSTER_REVIEW",
                        "reason": "Deterministic demo checks completed; human review required"},
                        f"demo:ready:{len(package['investigation']['transitions'])}:"
                        f"{sum(t['status'] == 'RESOLVED' for t in package['tasks'])}")
