"""Verify saved approvals independently of the SuccessRecord's own assertions."""
from datetime import datetime
import json
from .publication_contract import canonical, require, sha


def verify(snapshot, record, receipt, *, offline, trusted_approvals=None):
    digest = record.get('approvalSha256')
    require(isinstance(digest, str) and len(digest) == 64, 'Success approval proof missing')
    body = snapshot.files.get('approvals/'+digest+'.json')
    require(body is not None and sha(body) == digest, 'Success approval bytes missing or corrupted')
    approval = json.loads(body)
    require(approval.get('schemaVersion') == 1, 'Unknown saved approval schema')
    if approval.get('authorityKind') == 'offline-test':
        require(offline, 'Offline approval cannot certify a remote success')
    else:
        # A state writer cannot appoint itself an owner. Registry is supplied by
        # the reviewed authority integration, NEVER read from the candidate/state.
        require(approval.get('authorityKind') == 'owner-reviewed' and trusted_approvals is not None and
                trusted_approvals.get(digest) == body, 'Independent owner approval not trusted')
    require(approval.get('kind') == record['kind'] and approval.get('reference'), 'Approval origin/kind mismatch')
    from .publication_contract import digest
    digest(approval['publisher_sha'], 40)
    require(record['kind'] != 'publish' or approval['publisher_sha'] == receipt['provenance']['processorCommit'],
            'Approval publisher code mismatch')
    require(approval.get('zip_sha') == receipt['output']['siteZipSha256'] and
            approval.get('receipt_sha') == sha(canonical(receipt)) and
            approval.get('seed_sha') == receipt['frontend']['seedZipSha256'] and
            approval.get('code_sha') == receipt['provenance']['processorCommit'], 'Approval ZIP/receipt/seed/code binding mismatch')
    baseline = record.get('baseline')
    expected = (baseline['stateHead'], baseline['generation'], baseline['publishedZipSha256']) if baseline else (None, None, None)
    require(tuple(approval.get(k) for k in ('expected_head', 'expected_generation', 'expected_zip')) == expected,
            'Approval expected state binding mismatch')
    if record['kind'] == 'publish':
        require(baseline == receipt['baseline'], 'Success baseline differs from approved candidate')
    elif record['kind'] == 'legacy-import':
        require(baseline is None and record['pointer']['generation'] == 0, 'Invalid genesis approval')
        require(approval.get('deployment_id') == record['deployment']['id'], 'Genesis deployment not covered by owner approval')
    else:
        require(record['kind'] == 'manual-restore' and baseline is not None, 'Unsupported success authority')
    at = datetime.fromisoformat(record['at'])
    start = datetime.fromisoformat(approval['authorizedAt']); expiry = datetime.fromisoformat(approval['expires_at'])
    require(all(x.utcoffset() is not None for x in (at, start, expiry)) and start <= at < expiry,
            'Approval not valid at successful publication time')
    previous = record['pointer'].get('previous')
    if baseline:
        require(previous and previous['generation'] == baseline['generation'] and
                previous['publishedZipSha256'] == baseline['publishedZipSha256'], 'Approved previous state differs')
    return approval
