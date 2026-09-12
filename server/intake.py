"""Bind user-written claims to explicitly selected, locally available evidence."""
from uuid import uuid4
from agent_assets import CaseAssets
from agent_tools import AgentTools
from server.demo_assets import create_demo_assets
from server.integration import asset_root


LOCAL_FIELDS = [{
    'id': 'dewitt-demo-field', 'name': 'DeWitt demonstration field',
    'location': 'DeWitt County, Illinois', 'synthetic': True,
    'coverage': 'Synthetic field boundary, crop classification, rainfall and before/after imagery are stored locally.',
    'weather_start': '2026-06-19', 'weather_end': '2026-07-18',
    'before_date': '2026-05-30', 'after_date': '2026-08-12',
}]


def create_claim(service, body):
    reference = uuid4().hex
    if body.field_id == 'dewitt-demo-field':
        bundle = 'dewitt-synthetic-v1'
        assets = create_demo_assets(asset_root() / bundle)
        location, field, synthetic = LOCAL_FIELDS[0]['location'], LOCAL_FIELDS[0]['name'], True
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
    }
    return AgentTools.start(service, metadata, assets).investigation_id
