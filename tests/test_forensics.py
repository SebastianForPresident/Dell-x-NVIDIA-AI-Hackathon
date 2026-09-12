import csv
import io
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from forensics import crop_finding, ndvi_mean, parse_weather, vegetation_finding, weather_finding


class ForensicsTests(unittest.TestCase):
    def test_drought_requires_coverage_and_normal(self):
        day = date(2026, 7, 18)
        rows = [{"date": day-timedelta(days=i), "precipitation_mm": 1.0, "normal_mm": 3.0}
                for i in range(30)]
        self.assertEqual(weather_finding(rows, day).status, "supported")
        self.assertEqual(weather_finding(rows[:4], day).status, "inconclusive")
        rows[0]["normal_mm"] = None
        self.assertEqual(weather_finding(rows, day).status, "inconclusive")

    def test_flood_uses_different_rainfall_rule(self):
        day = date(2026, 7, 18)
        rows = [{"date": day-timedelta(days=i), "precipitation_mm": 5.0, "normal_mm": 3.0}
                for i in range(30)]
        self.assertEqual(weather_finding(rows, day, cause="Flood").status, "supported")
        self.assertEqual(weather_finding(rows, day, cause="Drought").status, "contradicted")

    def test_weather_csv_units(self):
        raw = b"date,precipitation,normal_precipitation\n2026-07-18,1,2\n"
        row = parse_weather(raw, "inches")[0]
        self.assertAlmostEqual(row["precipitation_mm"], 25.4)
        self.assertAlmostEqual(row["normal_mm"], 50.8)

    def test_raster_field_statistics(self):
        geometry = {"type": "Polygon", "coordinates": [[[0.2, 0.2], [0.8, 0.2],
                     [0.8, 0.8], [0.2, 0.8], [0.2, 0.2]]]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = {"driver": "GTiff", "height": 10, "width": 10, "count": 2,
                       "dtype": "float32", "crs": "EPSG:4326", "transform": from_origin(0, 1, 0.1, 0.1)}
            with rasterio.open(root / "image.tif", "w", **profile) as dataset:
                dataset.write(np.full((10, 10), 0.1, dtype="float32"), 1)
                dataset.write(np.full((10, 10), 0.3, dtype="float32"), 2)
            with rasterio.open(root / "cdl.tif", "w", **{**profile, "count": 1, "dtype": "uint8"}) as dataset:
                dataset.write(np.ones((10, 10), dtype="uint8"), 1)
            self.assertAlmostEqual(ndvi_mean(root / "image.tif", geometry, 1, 2), 0.5, places=5)
            self.assertEqual(crop_finding(root / "cdl.tif", geometry, "Corn").status, "supported")

    def test_image_dates_must_bracket_loss(self):
        finding = vegetation_finding(0.7, 0.4, date(2026, 5, 1), date(2026, 6, 1),
                                     date(2026, 7, 18), "test")
        self.assertEqual(finding.status, "inconclusive")


if __name__ == "__main__":
    unittest.main()
