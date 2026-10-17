"""Receipt v2 and complete packages, retaining the original candidate authority."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
from . import acquisition_state as acquisition
from .common import ROOT
from .publication_contract import (ASSETS, REPOSITORY, REPOSITORY_ID, ENVIRONMENT, canonical,
    sha, require, site_files, zip_bytes, read_zip, validate_receipt)
from .daily_release import identity, gate as data_gate, project, encoded
from .observation_release import check as observation_check

LEGACY_ZIP = '7621524742b25dfaa7a7216ca5f5b5006719a252966a0554ff7d0416c3262eee'
LEGACY_COMMIT = '82b1749a2626ce30d6196a101577b8bb09273c31'
LEGACY_DATA = 'bd5c0630bc3424e7c20aed05cf1f8801af90e34bd27563a9743615b907b1d7f9'


def _support(seed_zip, kind, effective_at, run_id, old_receipt):
    files = {'frontend-seed.zip': seed_zip, 'original-receipt.json': old_receipt,
             'projection.json': canonical({'kind': kind, 'effectiveAt': effective_at, 'runId': str(run_id)}),
             'code-inventory.json': canonical(acquisition.code_inventory())}
    files.update({'policies/'+n: b for n, b in acquisition.policy_files().items()})
    return zip_bytes(files)


def _receipt(files, seed, baseline, slot, provenance, gate, kind, original_receipt):
    public = site_files(files['site.zip']); m = json.loads(public['release-manifest.json'])
    internal_bytes = acquisition.unpack(files['acquisition-state.zip'])['market.json']
    internal = json.loads(internal_bytes)
    seed_files = site_files(seed)
    static = {n: sha(b) for n, b in seed_files.items() if n not in ('market.json', 'release-manifest.json')}
    pin = {'frontendId': 'legacy-4b1-static-inventory' if kind == 'legacy-import' else 'observation-daily-v1', 'assets': static}
    r = {'schemaVersion': 2, 'repository': REPOSITORY, 'repositoryId': REPOSITORY_ID,
         'environment': ENVIRONMENT, 'profile': 'observation-only', 'kind': kind,
         'baseline': baseline, 'slot': slot, 'provenance': {**provenance, 'inputSchemaVersion': internal['schemaVersion'],
             'parserSha256': acquisition.code_inventory()['pipeline/parsers.py'], 'schemaSha256': acquisition.code_inventory()['pipeline/schema.py']},
         'policies': {n: sha(b) for n, b in acquisition.policy_files().items()},
         'codeInventory': acquisition.code_inventory(),
         'frontend': {'seedZipSha256': sha(seed), 'frontendPinSha256': sha(canonical(pin)), 'assets': static,
                      'inventoryKind': 'derived-at-import' if kind == 'legacy-import' else 'daily-seed'},
         'output': {'siteZipSha256': sha(files['site.zip']), 'acquisitionZipSha256': sha(files['acquisition-state.zip']),
                    'supportZipSha256': sha(files['supporting-material.zip']), 'internalMarketSha256': sha(internal_bytes),
                    'publicMarketSha256': sha(public['market.json']), 'manifestSha256': sha(public['release-manifest.json']),
                    'sourceIdentitySha256': identity(internal),'originalReceiptSha256':sha(original_receipt)},
         'gate': gate, 'authority': {'deploymentAuthorized': False, 'rollbackAuthorized': False}}
    validate_receipt(r)
    return r


def verify_closure(files, expected_receipt_sha=None):
    require(set(files) == set(ASSETS), 'Incomplete package closure')
    receipt_bytes = files['candidate-receipt.json']
    if expected_receipt_sha is not None:
        require(sha(receipt_bytes) == expected_receipt_sha, 'Candidate receipt digest mismatch')
    r = validate_receipt(json.loads(receipt_bytes)); out = r['output']
    for name, field in [('site.zip', 'siteZipSha256'), ('acquisition-state.zip', 'acquisitionZipSha256'), ('supporting-material.zip', 'supportZipSha256')]:
        require(sha(files[name]) == out[field], 'Package digest mismatch: '+name)
    support = read_zip(files['supporting-material.zip'], lambda n: n in
        ('frontend-seed.zip', 'original-receipt.json', 'projection.json', 'code-inventory.json') or n in {'policies/'+x for x in acquisition.POLICIES})
    require(set(support) == {'frontend-seed.zip', 'original-receipt.json', 'projection.json', 'code-inventory.json'} |
            {'policies/'+x for x in acquisition.POLICIES}, 'Supporting closure incomplete')
    require(r['codeInventory'] == acquisition.code_inventory() == json.loads(support['code-inventory.json']), 'Frozen processor/formula changed')
    for n, b in acquisition.policy_files().items():
        require(support['policies/'+n] == b and r['policies'][n] == sha(b), 'Policy migration requires review: '+n)
    seed = support['frontend-seed.zip']
    require(sha(support['original-receipt.json']) == out['originalReceiptSha256'], 'Original receipt bytes changed')
    require(sha(seed) == r['frontend']['seedZipSha256'], 'Wrong historical seed ZIP')
    sf = site_files(seed); public = site_files(files['site.zip'])
    static = {n: sha(b) for n, b in sf.items() if n not in ('market.json', 'release-manifest.json')}
    require(static == r['frontend']['assets'] and all(sha(public[n]) == d for n, d in static.items()), 'Fixed frontend bytes changed')
    pin = {'frontendId': 'legacy-4b1-static-inventory' if r['kind'] == 'legacy-import' else 'observation-daily-v1', 'assets': static}
    require(sha(canonical(pin)) == r['frontend']['frontendPinSha256'], 'Frontend pin mismatch')
    internal_files = acquisition.unpack(files['acquisition-state.zip']); p = json.loads(internal_files['market.json'])
    require(sha(internal_files['market.json']) == out['internalMarketSha256'] and identity(p) == out['sourceIdentitySha256'], 'Internal/source identity mismatch')
    projection = json.loads(support['projection.json']); now = datetime.fromisoformat(projection['effectiveAt'])
    require(projection['kind'] == r['kind'] and projection['runId'] == str(r['provenance']['sourceRunId']), 'Projection provenance mismatch')
    m = json.loads(public['release-manifest.json'])
    if r['kind'] == 'legacy-import':
        require(sha(files['site.zip']) == LEGACY_ZIP and m['candidateCommit'] == LEGACY_COMMIT and
                sha(public['market.json']) == LEGACY_DATA and r['provenance']['processorCommit'] == LEGACY_COMMIT,
                'Unapproved legacy source')
        body, _ = observation_check(internal_files['market.json'], json.loads(support['policies/observation-release.json']), now=now)
        require(support['original-receipt.json'] == public['release-manifest.json'], 'Legacy original manifest altered')
    else:
        from .daily import quality
        require(r['gate']['runAttempt'] == r['provenance']['runAttempt'] and r['gate']['runId'] == str(r['provenance']['sourceRunId']) and
                r['gate']['baselineBinding'] == r['baseline'] and r['gate']['coverage'] == quality(p) and
                r['gate']['candidatePolicySha256'] == r['policies']['daily-release.json'] and r['gate']['intendedSlot'] == r['slot'], 'Gate/run/baseline binding mismatch')
        body, _ = project(p, projection['runId'], now)
        require(m['processorCommit'] == r['provenance']['processorCommit'] and m['runId'] == str(r['provenance']['sourceRunId']), 'Processor/run differs')
        require(m['sourceIdentitySha256'] == identity(p), 'Site source identity mismatch')
        require(m['productionBaselineVerified'] is False and m['candidatePolicySha256'] == r['policies']['daily-release.json'], 'Candidate authority/policy mismatch')
        old = json.loads(support['original-receipt.json'])
        require(old['zipSha256'] == out['siteZipSha256'] and old['dataSha256'] == out['publicMarketSha256'], 'Original receipt differs')
        # Reuse the complete existing daily bundle validator, including sourceVersions,
        # disabled scope, policy hashes and exact static inventory in the manifest.
        from .daily_release import verify_bundle_bytes
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for n in static:
                path = root/n; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(sf[n])
            (root/'frontend-pin.json').write_bytes(canonical(pin))
            verify_bundle_bytes(files['site.zip'],old,root)
    require(body == public['market.json'] and sha(public['market.json']) == out['publicMarketSha256'] and
            sha(public['release-manifest.json']) == out['manifestSha256'], 'Public projection cannot be reproduced')
    return r


def legacy_import_plan(site, data_dir, provenance, slot):
    """Build verified LOCAL materials only. Never initializes Releases/state or deploys."""
    public = site_files(site)
    require(sha(site) == LEGACY_ZIP, 'Exact original legacy ZIP required')
    files = {'site.zip': site, 'acquisition-state.zip': acquisition.pack(data_dir)}
    files['supporting-material.zip'] = _support(site, 'legacy-import', json.loads(public['market.json'])['generatedAt'],
                                              provenance['sourceRunId'], public['release-manifest.json'])
    r = _receipt(files, site, None, slot, provenance, {'decision': 'legacy-import'}, 'legacy-import',public['release-manifest.json'])
    files['candidate-receipt.json'] = canonical(r)
    verify_closure(files)
    return files


def prepare_candidate(baseline, candidate_dir, site_zip, seed_zip, expected_seed_sha, slot, provenance,*,original_receipt):
    """Independent gate over full state, not a decision string supplied by an artifact."""
    from .verified_baseline import VerifiedBaseline
    require(isinstance(baseline, VerifiedBaseline), 'Verified successful baseline required')
    require(sha(seed_zip) == expected_seed_sha, 'Explicit seed SHA mismatch')
    candidate = Path(candidate_dir)
    require(not (candidate/'failure.json').exists(), 'Failure candidate')
    gate = json.loads((candidate/'gate.json').read_bytes())
    report = json.loads((candidate/'candidate-report.json').read_bytes())
    require(gate['decision'] == 'candidate' and gate['runId'] == str(provenance['sourceRunId']) == report['runId'], 'Candidate source run mismatch')
    require(provenance['runAttempt'] == gate['runAttempt'], 'Source run attempt mismatch')
    require(gate['baselineBinding'] == baseline.binding, 'Candidate baseline binding differs')
    require(gate['intendedSlot'] == slot, 'Original intended slot binding differs')
    acq = (candidate/'acquisition-state.zip').read_bytes()
    candidate_payload = json.loads(acquisition.unpack(acq)['market.json'])
    decision = data_gate(candidate_payload, baseline.payload, slot['targetDate'])
    require(decision == 'candidate' and gate['target'] == slot['targetDate'] and gate['coverage'] == __import__('pipeline.daily', fromlist=['quality']).quality(candidate_payload), 'Independent data gate mismatch')
    require(site_files(site_zip)['market.json'] == (candidate/'candidate-market.json').read_bytes(), 'Packaged public data differs')
    files = {'site.zip': site_zip, 'acquisition-state.zip': acq}
    require(isinstance(original_receipt,bytes),'Original daily receipt bytes required')
    files['supporting-material.zip'] = _support(seed_zip, 'publish', candidate_payload['generatedAt'], provenance['sourceRunId'], original_receipt)
    r = _receipt(files, seed_zip, baseline.binding, slot, provenance, gate, 'publish',original_receipt)
    files['candidate-receipt.json'] = canonical(r)
    verify_closure(files)
    return files
