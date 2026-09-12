"""Fabricated case records for a transparent hackathon walkthrough."""

from datetime import date, timedelta

from forensics import Finding, build_report, neighbors_finding, vegetation_finding, weather_finding


def _boundary(lon: float, lat: float):
    def box(x0, y0, x1, y1):
        return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Claimed field"},
         "geometry": box(lon, lat, lon + 0.012, lat + 0.009)},
        {"type": "Feature", "properties": {"name": "Comparison field A"},
         "geometry": box(lon + 0.014, lat + 0.001, lon + 0.023, lat + 0.01)},
        {"type": "Feature", "properties": {"name": "Comparison field B"},
         "geometry": box(lon - 0.009, lat + 0.012, lon + 0.002, lat + 0.02)},
    ]}


def _case(case_id: str, farm: str, location: str, crop: str, cause: str, loss: date,
          rain_mm: float, normal_mm: float | None, before: float, after: float,
          neighbor_changes: list[float], coordinates: tuple[float, float], acreage: int,
          seed_state: str) -> dict:
    weather_rows = [{"date": loss - timedelta(days=29-i), "precipitation_mm": rain_mm / 30,
                     "normal_mm": normal_mm / 30 if normal_mm is not None else None}
                    for i in range(30)]
    before_date, after_date = loss - timedelta(days=42), loss + timedelta(days=25)
    crop_finding = Finding("Crop type", "supported", f"Dominant synthetic CDL class: {crop} (92% of sampled pixels).",
                           "Synthetic crop-layer sample", {"class": crop, "share": 0.92, "pixels": 460})
    weather = weather_finding(weather_rows, loss, cause=cause)
    weather.source = "Synthetic daily weather and normals"
    vegetation = vegetation_finding(before, after, before_date, after_date, loss,
                                     "Synthetic red/NIR field pixels")
    neighbors = neighbors_finding(neighbor_changes)
    neighbors.source = "Synthetic comparison fields"
    report = build_report(case_id, cause, loss, "Claimed field",
                          [crop_finding, weather, vegetation, neighbors], demo=True)
    values = [before, before - 0.02, before - 0.05,
              round((before + after) / 2, 3), after + 0.04, after]
    ndvi_dates = [before_date + timedelta(days=i * (after_date - before_date).days // 5)
                  for i in range(6)]
    return {
        "id": case_id, "farm": farm, "location": location, "crop": crop,
        "cause": cause, "loss_date": loss.isoformat(), "acreage": acreage,
        "created_at": (loss + timedelta(days=31)).isoformat(),
        "status": seed_state, "synthetic_demo": True, "origin": "seed",
        "boundary": _boundary(*coordinates), "selected_field": 0,
        "weather_series": [{"date": r["date"].isoformat(), "rainfall": round(r["precipitation_mm"], 2),
                            "normal": round(r["normal_mm"], 2) if r["normal_mm"] is not None else None}
                           for r in weather_rows],
        "ndvi_series": [{"date": day.isoformat(), "ndvi": round(value, 3)}
                        for day, value in zip(ndvi_dates, values)],
        "report": report, "narrative": None,
        "documents": ["Claim_SYNTHETIC.pdf", "FieldBoundary_SYNTHETIC.geojson",
                      "Satellite_Before_SYNTHETIC.tif", "Satellite_After_SYNTHETIC.tif",
                      "Weather_SYNTHETIC.csv", "CropLayer_SYNTHETIC.tif"],
        "workflow": [
            {"stage": "Claim intake", "detail": "Reported cause and field identified", "state": "complete"},
            {"stage": "Weather review", "detail": "30-day precipitation window compared", "state": "complete"},
            {"stage": "Crop verification", "detail": "Dominant crop-layer class measured", "state": "complete"},
            {"stage": "Imagery comparison", "detail": "NDVI change and nearby fields measured", "state": "complete"},
            {"stage": "Evidence package", "detail": "Structured report assembled", "state": "complete"},
        ],
    }


def demo_cases() -> list[dict]:
    return [
        _case("CI-2026-0418", "Mason Creek Farms", "Tompkins County, NY", "Corn",
              "Drought", date(2026, 7, 18), 30, 90, 0.72, 0.44,
              [-0.19, -0.22], (-76.50, 42.45), 184, "Evidence ready"),
        _case("CI-2026-0419", "Silver Run Cooperative", "Seneca County, NY", "Soybeans",
              "Flood", date(2026, 8, 4), 162, 90, 0.66, 0.47,
              [-0.14, -0.04], (-76.82, 42.78), 126, "Evidence ready"),
        _case("CI-2026-0420", "Westbrook Family Farm", "Cayuga County, NY", "Corn",
              "Drought", date(2026, 7, 29), 48, None, 0.64, 0.61,
              [-0.02, 0.01], (-76.56, 42.92), 97, "Needs review"),
    ]
