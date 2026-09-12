"""Bind loss reports to carrier-registered insured fields and local evidence."""
import json
from uuid import uuid4

from agent_assets import CaseAssets
from agent_tools import AgentTools
from server.demo_assets import create_demo_assets
from server.field_registry import insured_field, public_catalog
from server.integration import asset_root


LOCAL_FIELDS = public_catalog() + [{
    'id': 'dewitt-demo-field', 'field_id': 'dewitt-demo-field',
    'farm_id': 'synthetic-fixtures', 'farm_name': 'Synthetic regression fixtures',
    'name': 'DeWitt synthetic field', 'location': 'DeWitt County, Illinois', 'synthetic': True,
    'evidence_available': True,
    'coverage': 'Synthetic boundary, crop classification, rainfall and imagery for regression testing.',
    'weather_start': '2026-06-19', 'weather_end': '2026-07-18',
    'before_date': '2026-05-30', 'after_date': '2026-08-12', 'default_loss_date': '2026-07-18',
}]


def _registered_assets(record, reference):
    boundary_provenance = {
        'provider': 'Fictional carrier registry', 'product': 'Demo insured-field boundary',
        'field_id': record['field_id'], 'field_name': record['field_name'],
        'policy_id': record['policy_id'],
        'note': 'Fictional hackathon carrier record; not a real policyholder boundary.'}
    if not record.get('evidence_package_id'):
        bundle = f"registry-{record['field_id'].lower()}-{reference}"
        folder = asset_root() / bundle
        folder.mkdir()
        boundary = {"type": "FeatureCollection", "features": [{"type": "Feature",
            "properties": {"name": record['field_name'], "role": "insured",
                           "source": "Fictional carrier field registry"},
            "geometry": record['geometry']}]}
        (folder / 'field_context.geojson').write_text(json.dumps(boundary, sort_keys=True))
        return bundle, CaseAssets(folder, boundary='field_context.geojson',
                                  provenance={'boundary': boundary_provenance})

    bundle = record['evidence_package_id']
    folder = asset_root() / bundle
    source_manifest = json.loads((folder / 'source_manifest.json').read_text())
    evidence = record['evidence']
    provenance = dict(source_manifest['datasets'])
    provenance['boundary'] = boundary_provenance
    return bundle, CaseAssets(folder,
        boundary=evidence.get('boundary'), weather=evidence.get('weather'), crop=evidence.get('crop'),
        before=evidence.get('before'), after=evidence.get('after'),
        before_date=evidence.get('before_date'), after_date=evidence.get('after_date'),
        provenance=provenance)


def create_claim(service, body):
    reference = uuid4().hex
    requested_field = 'FIELD-17' if body.field_id == 'dewitt-public-2025' else body.field_id
    carrier = None
    if requested_field not in {'dewitt-demo-field', 'unregistered'}:
        carrier = insured_field(requested_field)
        bundle, assets = _registered_assets(carrier, reference)
        location, field, farm, synthetic = (carrier['location'], carrier['field_name'],
                                             carrier['farm_name'], False)
    elif requested_field == 'dewitt-demo-field':
        bundle = 'dewitt-synthetic-v1'
        assets = create_demo_assets(asset_root() / bundle)
        location, field, farm, synthetic = ('DeWitt County, Illinois', 'Synthetic corn field',
                                             body.farm or 'Synthetic demonstration farm', True)
    else:
        if not body.location:
            raise ValueError('Enter the location of the field without local coverage.')
        bundle = reference
        folder = asset_root() / bundle
        folder.mkdir()
        assets = CaseAssets(folder)
        location, field, farm, synthetic = (body.location, 'Field boundary not yet registered',
                                             body.farm or 'Unregistered farm', False)

    metadata = {
        'claim_id': body.claim_id or 'CLM-' + reference[:8].upper(),
        'farm': farm, 'claim_description': body.description,
        'reported_cause': body.cause, 'claimed_crop': body.crop,
        'reported_loss_date': body.loss_date.isoformat(), 'field': field,
        'location': location, 'synthetic_demo': synthetic,
        'asset_bundle': bundle, 'origin': 'intake', 'intake_id': reference,
        'claim_scenario': 'fictional' if carrier else None,
        'local_evidence_available': bool(carrier and carrier.get('evidence_package_id')),
    }
    if carrier:
        metadata.update({key: carrier[key] for key in (
            'policy_id', 'farm_id', 'field_id', 'field_name', 'crop_year', 'insured_crop', 'insured_acres')})
    return AgentTools.start(service, metadata, assets).investigation_id
