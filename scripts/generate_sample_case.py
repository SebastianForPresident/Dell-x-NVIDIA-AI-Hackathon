"""Create an explicitly synthetic case to exercise the upload workflow."""

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin


ROOT = Path(__file__).resolve().parents[1] / "sample_case"
ROOT.mkdir(exist_ok=True)

features = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"name": "North corn field"},
         "geometry": {"type": "Polygon", "coordinates": [[[-76.5, 42.45], [-76.49, 42.45], [-76.49, 42.46], [-76.5, 42.46], [-76.5, 42.45]]]}},
        {"type": "Feature", "properties": {"name": "Adjacent corn field"},
         "geometry": {"type": "Polygon", "coordinates": [[[-76.488, 42.45], [-76.478, 42.45], [-76.478, 42.46], [-76.488, 42.46], [-76.488, 42.45]]]}},
    ],
}
(ROOT / "FieldBoundary.geojson").write_text(json.dumps(features, indent=2))

with (ROOT / "Weather_SYNTHETIC.csv").open("w", newline="") as output:
    writer = csv.writer(output)
    writer.writerow(["date", "precipitation", "normal_precipitation"])
    for i in range(30):
        writer.writerow([(date(2026, 7, 18) - timedelta(days=29-i)).isoformat(), 1.0, 3.0])

height, width = 40, 60
transform = from_origin(-76.505, 42.465, 0.00055, 0.00055)
profile = {"driver": "GTiff", "height": height, "width": width, "count": 2,
           "dtype": "float32", "crs": "EPSG:4326", "transform": transform}
red = np.full((height, width), 0.1, dtype="float32")
for filename, nir_value in [("Satellite_May_SYNTHETIC.tif", 0.614),
                            ("Satellite_August_SYNTHETIC.tif", 0.257)]:
    with rasterio.open(ROOT / filename, "w", **profile) as dataset:
        dataset.write(red, 1)
        dataset.write(np.full((height, width), nir_value, dtype="float32"), 2)

with rasterio.open(ROOT / "CropLayer_SYNTHETIC.tif", "w", **{**profile, "count": 1, "dtype": "uint8"}) as dataset:
    dataset.write(np.ones((height, width), dtype="uint8"), 1)

(ROOT / "README.txt").write_text(
    "SYNTHETIC HACKATHON DEMO DATA. These are fabricated values and geometries near Ithaca, NY; "
    "they are not NOAA, USDA, or satellite observations.\n"
    "Upload loss date 2026-07-18, crop Corn, before image date 2026-05-30, "
    "after image date 2026-08-12; red band 1, NIR band 2.\n"
)
print(ROOT)
