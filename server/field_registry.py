"""Read the local carrier field registry used to bind claims to insured geometry."""
from __future__ import annotations

import json
import os
from pathlib import Path

from forensics import load_boundary


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "data" / "carrier_registry" / "insured_fields.json"


def registry_path() -> Path:
    return Path(os.environ.get("CARRIER_REGISTRY_PATH", DEFAULT_REGISTRY)).resolve(strict=True)


def insured_fields() -> list[dict]:
    data = json.loads(registry_path().read_text())
    fields = data.get("fields")
    if not isinstance(fields, list):
        raise ValueError("Carrier registry must contain a fields list.")
    seen = set()
    required = {"policy_id", "farm_id", "farm_name", "field_id", "field_name", "crop_year",
                "insured_crop", "insured_acres", "location", "geometry", "evidence_package_id"}
    for record in fields:
        if not required <= record.keys() or record["field_id"] in seen:
            raise ValueError("Carrier registry contains an invalid or duplicate field record.")
        seen.add(record["field_id"])
        load_boundary(json.dumps(record["geometry"]).encode())
    return fields


def insured_field(field_id: str) -> dict:
    record = next((item for item in insured_fields() if item["field_id"] == field_id), None)
    if record is None:
        raise ValueError("Unknown insured field.")
    return record


def public_catalog() -> list[dict]:
    result = []
    for record in insured_fields():
        evidence = record.get("evidence") or {}
        result.append({
            "id": record["field_id"], "field_id": record["field_id"], "name": record["field_name"],
            "farm_id": record["farm_id"], "farm_name": record["farm_name"],
            "policy_id": record["policy_id"], "location": record["location"],
            "insured_crop": record["insured_crop"], "insured_acres": record["insured_acres"],
            "crop_year": record["crop_year"], "synthetic": False,
            "evidence_available": bool(record.get("evidence_package_id")),
            "coverage": ("Public crop, weather, and satellite evidence is cached locally."
                         if record.get("evidence_package_id") else
                         "Carrier field is registered; public evidence is not cached locally for this field."),
            "weather_start": evidence.get("weather_start"), "weather_end": evidence.get("weather_end"),
            "before_date": evidence.get("before_date"), "after_date": evidence.get("after_date"),
            "default_loss_date": evidence.get("default_loss_date"),
        })
    return result
