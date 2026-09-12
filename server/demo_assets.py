"""Tiny fabricated DeWitt demo assets; no authoritative observations."""

import csv
import json
from datetime import date, timedelta

import numpy as np
import rasterio
from rasterio.transform import from_origin

from agent_assets import CaseAssets


def create_demo_assets(root):
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "complete.json").exists():
        def field(lon):
            return {"type": "Feature", "properties": {"name": "Synthetic corn field"},
                    "geometry": {"type": "Polygon", "coordinates": [[[lon, 40.15], [lon + .005, 40.15],
                    [lon + .005, 40.155], [lon, 40.155], [lon, 40.15]]]}}
        (root / "boundary.geojson").write_text(json.dumps({"type": "FeatureCollection",
            "features": [field(-88.90), field(-88.89)]}), encoding="utf-8")
        with (root / "weather.csv").open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["date", "precipitation", "normal_precipitation"])
            for i in range(30):
                writer.writerow([(date(2026, 7, 18) - timedelta(days=29-i)).isoformat(), 1, 3])
        profile = {"driver": "GTiff", "height": 30, "width": 30, "count": 2, "dtype": "float32",
                   "crs": "EPSG:4326", "transform": from_origin(-88.91, 40.17, .001, .001)}
        for filename, nir in (("before.tif", .7), ("after.tif", .25)):
            with rasterio.open(root / filename, "w", **profile) as dataset:
                dataset.write(np.full((30, 30), .1, dtype="float32"), 1)
                dataset.write(np.full((30, 30), nir, dtype="float32"), 2)
        with rasterio.open(root / "crop.tif", "w", **{**profile, "count": 1, "dtype": "uint8"}) as dataset:
            dataset.write(np.ones((30, 30), dtype="uint8"), 1)
        (root / "complete.json").write_text('{"synthetic_demo":true}', encoding="utf-8")
    return CaseAssets(root, boundary="boundary.geojson", weather="weather.csv", crop="crop.tif",
                      before="before.tif", after="after.tif", before_date="2026-05-30", after_date="2026-08-12")
