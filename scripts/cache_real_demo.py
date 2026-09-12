"""Cache and prepare traceable public evidence for the primary local demo.

Network access is required only while running this script. Runtime analysis uses
the resulting local files. The study areas are derived from USDA CDL corn
pixels; they are not cadastral parcels or asserted ownership boundaries.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import urllib.request
import zipfile

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.mask import mask
from rasterio.warp import transform_geom


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "case_assets" / "dewitt-public-2025-v1"
WORK = ROOT / ".runtime" / "source-downloads"
CDL_URL = "https://nassgeodata.gmu.edu/nass_data_cache/byfips/CDL_2025_17.zip"
GHCN_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/USW00003887.dly"
STAC_URL = "https://earth-search.aws.element84.com/v1"
SCENES = {
    "before": {
        "id": "S2A_16TCK_20250809_0_L2A", "date": "2025-08-09",
        "red": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/16/T/CK/2025/8/S2A_16TCK_20250809_0_L2A/B04.tif",
        "nir": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/16/T/CK/2025/8/S2A_16TCK_20250809_0_L2A/B08.tif",
    },
    "after": {
        "id": "S2C_16TCK_20250926_0_L2A", "date": "2025-09-26",
        "red": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/16/T/CK/2025/9/S2C_16TCK_20250926_0_L2A/B04.tif",
        "nir": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/16/T/CK/2025/9/S2C_16TCK_20250926_0_L2A/B08.tif",
    },
}
AOI = {"type": "Polygon", "coordinates": [[[-88.92, 40.13], [-88.86, 40.13],
        [-88.86, 40.18], [-88.92, 40.18], [-88.92, 40.13]]]}
LOSS_DATE = date(2025, 9, 18)


def download(url: str, path: Path, insecure=False):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    context = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(url, context=context) as response, path.open("wb") as output:
        shutil.copyfileobj(response, output)


def sha256(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_cdl():
    archive = WORK / "CDL_2025_17.zip"
    download(CDL_URL, archive, insecure=True)  # Source host certificate expired in 2026.
    with zipfile.ZipFile(archive) as zipped:
        tif = next(name for name in zipped.namelist() if name.lower().endswith(".tif"))
        source = WORK / Path(tif).name
        if not source.exists():
            zipped.extract(tif, WORK)
            extracted = WORK / tif
            if extracted != source:
                extracted.replace(source)
    with rasterio.open(source) as dataset:
        geom = transform_geom("EPSG:4326", dataset.crs, AOI)
        data, transform = mask(dataset, [geom], crop=True, filled=True, nodata=0)
        profile = dataset.profile.copy()
        profile.update(height=data.shape[1], width=data.shape[2], transform=transform,
                       compress="deflate", nodata=0)
        with rasterio.open(CACHE / "usda_cdl_2025.tif", "w", **profile) as out:
            out.write(data)
        corn = data[0] == 1
        candidates = []
        for geometry, value in shapes(corn.astype("uint8"), mask=corn, transform=transform):
            if value == 1:
                pixels = int(round(rasterio.features.geometry_mask([geometry], corn.shape,
                             transform, invert=True).sum()))
                if pixels >= 80:
                    candidates.append((pixels, transform_geom(dataset.crs, "EPSG:4326", geometry)))
        candidates.sort(reverse=True, key=lambda item: item[0])
        if len(candidates) < 2:
            raise RuntimeError("AOI does not contain two usable USDA-derived corn areas")
        features = []
        for index, (pixels, geometry) in enumerate(candidates[:3]):
            features.append({"type": "Feature", "properties": {
                "name": "Selected crop analysis area" if index == 0 else f"Comparison crop area {index}",
                "role": "analysis" if index == 0 else "comparison",
                "derived_from": "USDA NASS Cropland Data Layer 2025; contiguous CDL class 1 pixels",
                "cdl_pixels": pixels,
            }, "geometry": geometry})
        (CACHE / "analysis_areas.geojson").write_text(json.dumps({
            "type": "FeatureCollection", "features": features,
            "provenance": {"provider": "USDA NASS", "product": "Cropland Data Layer",
                "year": 2025, "source_url": CDL_URL,
                "note": "Analysis areas derived from classified corn pixels; not cadastral parcels."}}, indent=2))


def prepare_sentinel(key: str):
    scene = SCENES[key]
    geometry = json.loads((CACHE / "analysis_areas.geojson").read_text())
    extent = {"type": "FeatureCollection", "features": geometry["features"]}
    arrays = []
    out_profile = None
    for asset in ("red", "nir"):
        with rasterio.open(scene[asset]) as source:
            geoms = [transform_geom("EPSG:4326", source.crs, f["geometry"]) for f in extent["features"]]
            data, transform = mask(source, geoms, crop=True, filled=True, nodata=0)
            arrays.append(data[0])
            out_profile = source.profile.copy()
            out_profile.update(height=data.shape[1], width=data.shape[2], transform=transform,
                               count=2, compress="deflate", nodata=0)
    with rasterio.open(CACHE / f"sentinel2_{key}.tif", "w", **out_profile) as output:
        output.write(arrays[0], 1)
        output.write(arrays[1], 2)


def parse_dly(path: Path):
    values = {}
    for line in path.read_text().splitlines():
        if line[17:21] != "PRCP":
            continue
        year, month = int(line[11:15]), int(line[15:17])
        for day in range(1, 32):
            try:
                observed = date(year, month, day)
            except ValueError:
                continue
            value = int(line[21 + (day - 1) * 8:26 + (day - 1) * 8])
            if value >= 0:
                values[observed] = value / 10  # GHCN PRCP tenths of mm.
    return values


def prepare_weather():
    source = WORK / "USW00003887.dly"
    download(GHCN_URL, source)
    values = parse_dly(source)
    start = LOSS_DATE - timedelta(days=29)
    with (CACHE / "noaa_ghcn_daily.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["date", "precipitation", "normal_precipitation"])
        for offset in range(30):
            day = start + timedelta(days=offset)
            historical = [values[day.replace(year=year)] for year in range(1991, 2021)
                          if day.replace(year=year) in values]
            normal = sum(historical) / len(historical) if historical else None
            writer.writerow([day.isoformat(), values.get(day, ""),
                             "" if normal is None else f"{normal:.4f}"])
    return source


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    prepare_cdl()
    for key in SCENES:
        prepare_sentinel(key)
    ghcn = prepare_weather()
    assets = [CACHE / name for name in ("analysis_areas.geojson", "usda_cdl_2025.tif",
        "sentinel2_before.tif", "sentinel2_after.tif", "noaa_ghcn_daily.csv")]
    manifest = {
        "package_id": "dewitt-public-2025-v1", "claim_scenario": "fictional",
        "analysis_area": "CDL-derived crop analysis area; not a parcel boundary",
        "loss_date": LOSS_DATE.isoformat(),
        "datasets": {
            "crop": {"provider": "USDA NASS", "product": "Cropland Data Layer", "year": 2025,
                     "url": CDL_URL, "local_file": "usda_cdl_2025.tif"},
            "weather": {"provider": "NOAA NCEI", "product": "GHCN-Daily",
                "station_id": "USW00003887", "station_name": "Decatur Airport, Illinois",
                "window": ["2025-08-20", "2025-09-18"], "baseline": "1991–2020 daily means from the same station record",
                "url": GHCN_URL, "source_sha256": sha256(ghcn), "local_file": "noaa_ghcn_daily.csv"},
            "before": {"provider": "Copernicus/ESA", "product": "Sentinel-2 MSI Level-2A BOA reflectance",
                       "item_id": SCENES["before"]["id"], "date": SCENES["before"]["date"],
                       "catalog": STAC_URL, "local_file": "sentinel2_before.tif"},
            "after": {"provider": "Copernicus/ESA", "product": "Sentinel-2 MSI Level-2A BOA reflectance",
                      "item_id": SCENES["after"]["id"], "date": SCENES["after"]["date"],
                      "catalog": STAC_URL, "local_file": "sentinel2_after.tif"},
        },
        "processing": {"crop": "Dominant CDL class inside USDA-derived analysis geometry",
                       "weather": "30-day total and sum of 1991–2020 calendar-day means",
                       "vegetation": "Mean NDVI=(B08-B04)/(B08+B04) over valid pixels"},
        "files": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in assets},
    }
    (CACHE / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
