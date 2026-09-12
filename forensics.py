"""Deterministic, local evidence extraction for crop-loss investigations."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    check: str
    status: str  # supported, contradicted, inconclusive, unavailable
    detail: str
    source: str
    values: dict[str, Any]


CDL_CROPS = {
    1: "Corn", 5: "Soybeans", 4: "Sorghum", 21: "Barley",
    22: "Durum wheat", 23: "Spring wheat", 24: "Winter wheat",
    36: "Alfalfa", 37: "Other hay", 61: "Fallow/idle cropland",
}


def load_boundary(raw: bytes) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    else:
        features = [{"type": "Feature", "geometry": data, "properties": {}}]
    features = [f for f in features if f.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"}]
    if not features:
        raise ValueError("GeoJSON must contain at least one Polygon or MultiPolygon feature.")
    return features


def field_names(features: list[dict[str, Any]]) -> list[str]:
    return [str(f.get("properties", {}).get("name") or f.get("properties", {}).get("id") or f"Field {i+1}")
            for i, f in enumerate(features)]


def parse_weather(raw: bytes, unit: str = "mm") -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames:
        raise ValueError("Weather CSV is empty.")
    needed = {"date", "precipitation"}
    if not needed.issubset(set(reader.fieldnames)):
        raise ValueError("Weather CSV needs date and precipitation columns; normal_precipitation is optional.")
    factor = 25.4 if unit == "inches" else 1.0
    rows = []
    for row in reader:
        try:
            day = date.fromisoformat(row["date"].strip())
            precip = float(row["precipitation"]) * factor
            normal = row.get("normal_precipitation", "").strip()
            normal_mm = float(normal) * factor if normal else None
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid weather row: {row}") from exc
        if precip < 0 or (normal_mm is not None and normal_mm < 0):
            raise ValueError("Precipitation values cannot be negative.")
        rows.append({"date": day, "precipitation_mm": precip, "normal_mm": normal_mm})
    if len({r["date"] for r in rows}) != len(rows):
        raise ValueError("Weather CSV has duplicate dates.")
    return sorted(rows, key=lambda r: r["date"])


def weather_finding(rows: list[dict[str, Any]], loss_date: date, window_days: int = 30,
                    cause: str = "Drought") -> Finding:
    start = loss_date - timedelta(days=window_days - 1)
    selected = [r for r in rows if start <= r["date"] <= loss_date]
    coverage = len(selected) / window_days
    if not selected:
        return Finding("Precipitation", "unavailable", "No weather observations in the claim window.",
                       "Uploaded weather CSV", {"window_start": start.isoformat(), "window_end": loss_date.isoformat()})
    actual = sum(r["precipitation_mm"] for r in selected)
    normals = [r["normal_mm"] for r in selected]
    values = {"window_start": start.isoformat(), "window_end": loss_date.isoformat(),
              "days_observed": len(selected), "days_expected": window_days,
              "rainfall_mm": round(actual, 1)}
    if coverage < 0.8:
        return Finding("Precipitation", "inconclusive",
                       f"Only {len(selected)}/{window_days} days covered; rainfall total is {actual:.1f} mm.",
                       "Uploaded weather CSV", values)
    if any(n is None for n in normals):
        return Finding("Precipitation", "inconclusive",
                       f"Rainfall was {actual:.1f} mm over {len(selected)} days; no matched normal was provided, so a deficit cannot be established.",
                       "Uploaded weather CSV", values)
    expected = sum(normals)
    ratio = actual / expected if expected > 0 else None
    values.update({"normal_mm": round(expected, 1), "percent_of_normal": round(ratio * 100, 1) if ratio is not None else None})
    if ratio is None:
        status = "inconclusive"
        detail = "The matched precipitation normal is zero."
    elif cause.lower() == "drought" and ratio <= 0.6:
        status = "supported"
        detail = f"Rainfall was {actual:.1f} mm versus {expected:.1f} mm normal ({ratio:.0%} of normal)."
    elif cause.lower() == "drought":
        status = "contradicted"
        detail = f"Rainfall was {actual:.1f} mm versus {expected:.1f} mm normal ({ratio:.0%} of normal); no severe deficit by the demo threshold (≤60%)."
    elif cause.lower() == "flood" and ratio >= 1.5:
        status = "supported"
        detail = f"Rainfall was {actual:.1f} mm versus {expected:.1f} mm normal ({ratio:.0%} of normal). This is elevated rainfall, not proof of field flooding."
    elif cause.lower() == "flood":
        status = "contradicted"
        detail = f"Rainfall was {actual:.1f} mm versus {expected:.1f} mm normal ({ratio:.0%} of normal); no elevated 30-day rainfall by the demo threshold (≥150%). Short storms may still be missed."
    else:
        status = "inconclusive"
        detail = f"Rainfall was {actual:.1f} mm versus {expected:.1f} mm normal ({ratio:.0%} of normal); no screening rule is defined for this cause."
    return Finding("Precipitation", status, detail, "Uploaded weather CSV", values)


def vegetation_finding(before: float | None, after: float | None, before_date: date, after_date: date,
                       loss_date: date, source: str) -> Finding:
    if before is None or after is None:
        return Finding("Vegetation change", "unavailable", "Insufficient valid red/NIR pixels in one or both images.", source, {})
    change = after - before
    values = {"before_ndvi": round(before, 3), "after_ndvi": round(after, 3),
              "change": round(change, 3), "before_date": before_date.isoformat(), "after_date": after_date.isoformat()}
    if not (before_date < loss_date <= after_date):
        return Finding("Vegetation change", "inconclusive",
                       f"NDVI changed from {before:.3f} to {after:.3f}, but the images do not bracket the reported loss date.", source, values)
    if change <= -0.12:
        return Finding("Vegetation change", "supported",
                       f"Mean NDVI fell from {before:.3f} to {after:.3f} ({change:+.3f}) across the claim date.", source, values)
    return Finding("Vegetation change", "contradicted",
                   f"Mean NDVI changed from {before:.3f} to {after:.3f} ({change:+.3f}); no marked decline by the demo threshold (≤−0.12).", source, values)


def _masked_raster(path: str | Path, geometry: dict[str, Any], bands: tuple[int, ...]):
    import numpy as np
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"{Path(path).name} has no coordinate reference system.")
        if max(bands) > dataset.count:
            raise ValueError(f"{Path(path).name} has {dataset.count} bands; requested band {max(bands)}.")
        shape = transform_geom("EPSG:4326", dataset.crs, geometry)
        arrays, _ = mask(dataset, [shape], indexes=list(bands), crop=True, filled=False)
        return np.ma.asarray(arrays, dtype="float64")


def ndvi_mean(path: str | Path, geometry: dict[str, Any], red_band: int, nir_band: int) -> float | None:
    import numpy as np

    bands = _masked_raster(path, geometry, (red_band, nir_band))
    red, nir = bands[0], bands[1]
    denominator = red + nir
    valid = (~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir) &
             np.isfinite(red) & np.isfinite(nir) & (denominator > 0))
    if not np.any(valid):
        return None
    ndvi = (nir[valid] - red[valid]) / denominator[valid]
    ndvi = ndvi[np.isfinite(ndvi)]
    return float(np.mean(ndvi)) if len(ndvi) else None


def crop_finding(path: str | Path, geometry: dict[str, Any], expected_crop: str) -> Finding:
    import numpy as np

    values = _masked_raster(path, geometry, (1,))[0].compressed()
    if not len(values):
        return Finding("Crop type", "unavailable", "No valid CDL pixels intersect this field.", str(path), {})
    codes, counts = np.unique(values.astype(int), return_counts=True)
    winner = int(codes[np.argmax(counts)])
    share = float(max(counts) / sum(counts))
    crop = CDL_CROPS.get(winner, f"CDL code {winner}")
    status = ("inconclusive" if expected_crop.strip().lower() == "other" else
              "supported" if crop.lower() == expected_crop.strip().lower() and share >= 0.5 else "contradicted")
    return Finding("Crop type", status, f"Dominant CDL class: {crop} ({share:.0%} of sampled pixels).",
                   str(path), {"cdl_code": winner, "class": crop, "share": round(share, 3), "pixels": int(sum(counts))})


def neighbors_finding(changes: list[float]) -> Finding:
    if not changes:
        return Finding("Other supplied fields", "unavailable", "No other field polygons with valid imagery were supplied.",
                       "Uploaded boundary and imagery", {})
    count = sum(change <= -0.12 for change in changes)
    status = "supported" if count >= len(changes) / 2 else "contradicted"
    return Finding("Other supplied fields", status,
                   f"{count}/{len(changes)} other supplied fields had NDVI declines ≤−0.12.",
                   "Uploaded boundary and imagery",
                   {"fields_checked": len(changes), "fields_with_decline": count,
                    "changes": [round(c, 3) for c in changes]})


def build_report(claim_id: str, cause: str, loss_date: date, field_name: str,
                 findings: list[Finding], demo: bool = False) -> dict[str, Any]:
    evidence = [asdict(f) for f in findings]
    status_counts = {status: sum(f.status == status for f in findings)
                     for status in ("supported", "contradicted", "inconclusive", "unavailable")}
    return {"claim_id": claim_id, "reported_cause": cause, "reported_loss_date": loss_date.isoformat(),
            "field": field_name, "synthetic_demo": demo, "findings": evidence,
            "evidence_summary": status_counts,
            "assessment": "Evidence review only. No coverage, causation, or claim decision is made.",
            "method": "Field means from valid red/NIR pixels; NDVI=(NIR-red)/(NIR+red). "
                      "Weather uses the 30 days ending on the reported loss date. "
                      "Demo thresholds: drought rainfall ≤60% of supplied normal; flood rainfall ≥150%; NDVI change ≤−0.12. "
                      "These screen for consistency, not cause or insurance coverage."}


def markdown_report(report: dict[str, Any]) -> str:
    label = " — SYNTHETIC DEMO" if report["synthetic_demo"] else ""
    lines = [f"# Crop insurance evidence package{label}", "",
             f"Claim: {report['claim_id']}  ", f"Field: {report['field']}  ",
             f"Reported cause: {report['reported_cause']}  ",
             f"Reported loss date: {report['reported_loss_date']}", "", "## Findings", ""]
    for finding in report["findings"]:
        lines += [f"### {finding['check']} — {finding['status'].title()}", "",
                  finding["detail"], "", f"Source: {finding['source']}", ""]
    lines += ["## Scope", "", report["assessment"], "", report["method"], ""]
    return "\n".join(lines)
