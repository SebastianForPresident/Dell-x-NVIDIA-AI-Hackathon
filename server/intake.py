"""Bind user-written claims to explicitly selected, locally available evidence."""
import json
from uuid import uuid4
from agent_assets import CaseAssets
from agent_tools import AgentTools
from server.demo_assets import create_demo_assets
from server.integration import asset_root


LOCAL_FIELDS = [{
    'id': 'dewitt-public-2025', 'name': 'DeWitt crop analysis area',
    'location': 'DeWitt County, Illinois', 'synthetic': False,
    'coverage': 'Cached USDA crop classification, NOAA station observations, and Copernicus Sentinel-2 imagery are stored locally.',
    'weather_start': '2025-08-20', 'weather_end': '2025-09-18',
    'before_date': '2025-08-09', 'after_date': '2025-09-26', 'default_loss_date': '2025-09-18',
}, {
    'id': 'dewitt-demo-field', 'name': 'DeWitt demonstration field',
    'location': 'DeWitt County, Illinois', 'synthetic': True,
    'coverage': 'Synthetic field boundary, crop classification, rainfall and before/after imagery are stored locally.',
    'weather_start': '2026-06-19', 'weather_end': '2026-07-18',
    'before_date': '2026-05-30', 'after_date': '2026-08-12',
}]


def create_claim(service, body):
    reference = uuid4().hex
    if body.field_id == 'dewitt-public-2025':
        bundle = 'dewitt-public-2025-v1'
        folder = asset_root() / bundle
        manifest = json.loads((folder / 'source_manifest.json').read_text())
        provenance = dict(manifest['datasets'])
        provenance['boundary'] = {
            'provider': 'USDA NASS', 'product': 'Cropland Data Layer 2025 derived analysis areas',
            'note': 'Crop analysis regions derived from contiguous classified pixels; not cadastral parcels.'}
        assets = CaseAssets(folder, boundary='analysis_areas.geojson', weather='noaa_ghcn_daily.csv',
            crop='usda_cdl_2025.tif', before='sentinel2_before.tif', after='sentinel2_after.tif',
            before_date='2025-08-09', after_date='2025-09-26', provenance=provenance)
        location, field, synthetic = LOCAL_FIELDS[0]['location'], LOCAL_FIELDS[0]['name'], False
    elif body.field_id == 'dewitt-demo-field':
        bundle = 'dewitt-synthetic-v1'
        assets = create_demo_assets(asset_root() / bundle)
        location, field, synthetic = LOCAL_FIELDS[1]['location'], LOCAL_FIELDS[1]['name'], True
    elif body.field_id == 'unregistered':
        if not body.location:
            raise ValueError('Enter the location of the field without local coverage.')
        bundle = reference
        folder = asset_root() / bundle
        folder.mkdir()
        assets = CaseAssets(folder)
        location, field, synthetic = body.location, 'Field boundary not yet registered', False
    else:
        raise ValueError('Unknown local field.')
    metadata = {
        'claim_id': body.claim_id or 'CLM-' + reference[:8].upper(),
        'farm': body.farm, 'claim_description': body.description,
        'reported_cause': body.cause, 'claimed_crop': body.crop,
        'reported_loss_date': body.loss_date.isoformat(), 'field': field,
        'location': location, 'synthetic_demo': synthetic,
        'asset_bundle': bundle, 'origin': 'intake', 'intake_id': reference,
        'claim_scenario': 'fictional' if body.field_id == 'dewitt-public-2025' else None,
    }
    return AgentTools.start(service, metadata, assets).investigation_id
