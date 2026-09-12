"""Case-bound tool dispatcher, ready for a verified OpenClaw registration adapter.

No model client, shell, network access, or autonomous loop lives here.
"""

from copy import deepcopy
from dataclasses import asdict
from datetime import date
import json
import math
import re

from forensics import (Finding, crop_finding, ndvi_mean, neighbors_finding,
                       parse_weather, vegetation_finding, weather_finding)
from investigations import stable_id


def tool(name, description, properties=None):
    properties = properties or {}
    return {"name": name, "description": description, "input_schema": {
        "type": "object", "properties": properties, "required": list(properties),
        "additionalProperties": False}}


TEXT = {"type": "string", "minLength": 1, "maxLength": 1000}
TOOL_SCHEMAS = [
    tool("get_claim", "Read this investigation's claim, workflow state, evidence inspected and open tasks."),
    tool("check_crop_classification", "Calculate dominant crop classification inside the claimed field."),
    tool("check_rainfall", "Calculate rainfall and matched-normal deficit for the claim's 30-day window."),
    tool("check_vegetation_change", "Calculate before/after field NDVI using approved image bands and dates."),
    tool("compare_neighboring_fields", "Calculate NDVI changes for other supplied field polygons."),
    tool("create_follow_up_task", "Create a human evidence follow-up task and mark NEEDS_EVIDENCE.",
         {"title": TEXT, "reason": TEXT}),
    tool("set_case_status", "Change investigation workflow status; never approve/deny a claim.",
         {"status": {"type": "string", "enum": ["INVESTIGATING", "NEEDS_EVIDENCE", "READY_FOR_ADJUSTER_REVIEW"]},
          "reason": TEXT}),
    tool("save_investigation_report", "Build and save an evidence report from all four persisted evidence checks."),
]


class AgentTools:
    def __init__(self, service, investigation_id, assets, actor="agent"):
        if actor not in {"agent", "demo"}:
            raise ValueError("Unsupported tool actor.")
        self.actor = actor
        self.service, self.investigation_id, self.assets = service, investigation_id, assets
        record = service.load_package(investigation_id)["investigation"]
        self.metadata = record["metadata"]
        self.manifest = assets.manifest()
        if record["context"].get("agent_asset_manifest") != self.manifest:
            raise ValueError("Assets do not match this investigation's registered manifest.")

    @classmethod
    def start(cls, service, metadata, assets, actor="agent"):
        """Trusted application entry point, not a model tool."""
        required = {"claim_id", "reported_cause", "reported_loss_date", "field", "claimed_crop", "synthetic_demo"}
        if not required <= metadata.keys():
            raise ValueError("Missing claim metadata.")
        if any(not isinstance(metadata[k], str) or not metadata[k].strip() for k in required - {"synthetic_demo"}):
            raise ValueError("Claim metadata must contain nonempty strings.")
        if type(metadata["synthetic_demo"]) is not bool:
            raise ValueError("synthetic_demo must explicitly be true or false.")
        date.fromisoformat(metadata["reported_loss_date"])
        manifest = assets.manifest()
        signature = stable_id("agent-tools-v1", metadata, manifest)
        key = service.start_investigation(metadata, signature, {"agent_asset_manifest": manifest})
        return cls(service, key, assets, actor=actor)

    def schemas(self):
        return deepcopy(TOOL_SCHEMAS)

    def invoke(self, name, arguments, call_id):
        """Runtime supplies a stable call ID; it is not a model argument.

        Audit unavailability raises: never tell the runtime an unaudited call succeeded.
        """
        if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", call_id):
            raise ValueError("Runtime call_id must be 1-128 letters, digits, _, ., :, or -.")
        if not isinstance(name, str) or len(name) > 100:
            raise ValueError("Runtime tool name must be a short string.")
        # Validate transport representation before storing anything in MongoDB.
        try:
            encoded = json.dumps(arguments, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ValueError("Arguments must be finite JSON values.") from exc
        if len(encoded) > 5000:
            raise ValueError("Tool arguments exceed 5000 characters.")
        action_key = "tool:" + call_id
        previous = self.service.get_recorded_action(self.investigation_id, action_key)
        if previous:
            if previous["tool"] != name or previous["arguments"] != arguments:
                result = {"ok": False, "error": {"code": "CALL_ID_CONFLICT", "message": "Call ID already used with different inputs."}}
                self.service.record_action(self.investigation_id,
                                           "conflict:" + stable_id(call_id, name, arguments),
                                           name, arguments, result, actor=self.actor)
                return result
            return previous["result"]
        try:
            schema = next((s for s in TOOL_SCHEMAS if s["name"] == name), None)
            if schema is None:
                raise ValueError("Unknown tool.")
            properties = schema["input_schema"]["properties"]
            if not isinstance(arguments, dict) or set(arguments) != set(properties):
                raise ValueError("Arguments must contain exactly the tool schema's required properties.")
            for key, spec in properties.items():
                value = arguments[key]
                if not isinstance(value, str) or not value.strip() or len(value) > spec.get("maxLength", 1000):
                    raise ValueError(f"{key} must be a nonempty string within its length limit.")
                if "enum" in spec and value not in spec["enum"]:
                    raise ValueError(f"Unsupported {key}.")
            if self.assets.manifest() != self.manifest:
                raise ValueError("Case assets changed. Register a new investigation before continuing.")
            result = {"ok": True, "data": self._execute(name, arguments)}
            json.dumps(result, allow_nan=False)
        except Exception as exc:
            # Do not expose absolute filesystem paths in error results.
            message = str(exc).replace(str(self.assets.root), "<case-assets>")
            code = "INVALID_INPUT_OR_EVIDENCE" if isinstance(exc, (ValueError, KeyError, TypeError)) else "TOOL_EXECUTION_ERROR"
            result = {"ok": False, "error": {"code": code, "message": message}}
        self.service.record_action(self.investigation_id, action_key, name, arguments, result, actor=self.actor)
        return result

    def _execute(self, name, args):
        key = self.investigation_id
        if name == "get_claim":
            package = self.service.load_package(key)
            return {"investigation_id": key, "claim": self.metadata,
                    "status": package["investigation"]["status"],
                    "evidence": [e["finding"] for e in package["evidence"]],
                    "open_tasks": [{"task_id": t["_id"], "title": t["title"], "reason": t["reason"]}
                                   for t in package["tasks"] if t["status"] == "OPEN"]}
        status = self.service.load_package(key)["investigation"]["status"]
        if name == "set_case_status":
            self.service.set_case_status(key, args["status"], args["reason"], actor=self.actor)
            return {"status": args["status"]}
        if status == "NEW":
            self.service.set_case_status(key, "INVESTIGATING", "Evidence investigation began", actor=self.actor)
        if name == "create_follow_up_task":
            task_id = self.service.create_follow_up_task(key, **args, actor=self.actor)
            package = self.service.load_package(key)
            task = next(t for t in package["tasks"] if t["_id"] == task_id)
            return {"task_id": task_id, "task_status": task["status"],
                    "status": package["investigation"]["status"]}
        if name == "save_investigation_report":
            return self.service.publish_agent_report(key)
        finding = self._finding(name)
        payload = asdict(finding)
        json.dumps(payload, allow_nan=False)
        evidence_id = self.service.record_evidence(key, payload)
        return {"evidence_id": evidence_id, "finding": payload}

    def _finding(self, name):
        assets = self.assets
        labels = {"check_crop_classification": "Crop type", "check_rainfall": "Precipitation",
                  "check_vegetation_change": "Vegetation change", "compare_neighboring_fields": "Other supplied fields"}
        label = labels[name]
        loss_date = date.fromisoformat(self.metadata["reported_loss_date"])

        def missing(detail):
            return Finding(label, "unavailable", detail, "Registered case assets", {})

        provenance = assets.provenance or {}

        def sourced(finding, *dataset_keys):
            datasets = [deepcopy(provenance[key]) for key in dataset_keys if key in provenance]
            finding.provenance = {"datasets": datasets} if datasets else None
            if datasets:
                finding.source = "; ".join(
                    f"{item.get('provider', 'Unknown provider')} {item.get('product', 'dataset')}"
                    for item in datasets)
            return finding

        if name == "check_rainfall":
            path = assets.path("weather")
            if path is None:
                return missing("No weather CSV registered. Request weather observations and matched normals.")
            rows = parse_weather(path.read_bytes(), assets.weather_unit)
            if any(not math.isfinite(r["precipitation_mm"]) or
                   (r["normal_mm"] is not None and not math.isfinite(r["normal_mm"])) for r in rows):
                raise ValueError("Weather observations must be finite numbers.")
            finding = weather_finding(rows, loss_date, cause=self.metadata["reported_cause"])
            return sourced(finding, "weather")
        fields, geometry = assets.fields()
        if geometry is None:
            return missing("No field boundary registered. Request a field boundary.")
        if name == "check_crop_classification":
            path = assets.path("crop")
            if path is None:
                return missing("No crop classification raster registered.")
            finding = crop_finding(path, geometry, self.metadata["claimed_crop"])
            return sourced(finding, "crop")
        before, after = assets.path("before"), assets.path("after")
        if before is None or after is None or assets.before_date is None or assets.after_date is None:
            return missing("Before/after imagery and both image dates are required.")
        before_date, after_date = date.fromisoformat(assets.before_date), date.fromisoformat(assets.after_date)
        source = f"{self.manifest['before']['name']}; {self.manifest['after']['name']}"

        def change_for(shape):
            old = ndvi_mean(before, shape, assets.red_band, assets.nir_band)
            new = ndvi_mean(after, shape, assets.red_band, assets.nir_band)
            return old, new

        if name == "check_vegetation_change":
            old, new = change_for(geometry)
            return sourced(vegetation_finding(old, new, before_date, after_date, loss_date, source), "before", "after")
        if not before_date < loss_date <= after_date:
            return Finding(label, "inconclusive", "Neighbor imagery does not bracket the loss date.", source, {})
        changes = []
        invalid = 0
        for index, field in enumerate(fields):
            if index != assets.selected_field:
                old, new = change_for(field["geometry"])
                if old is None or new is None:
                    invalid += 1
                else:
                    changes.append(new - old)
        finding = neighbors_finding(changes)
        finding.source = source
        if invalid:
            finding.status = "inconclusive"
            finding.detail += f" {invalid} other field(s) had insufficient valid pixels."
            finding.values["fields_unavailable"] = invalid
        return sourced(finding, "before", "after", "boundary")
