"""Pure g0 preparation. No API/Git calls, authority issuance, or Pages writes."""
import json
from .candidate_package import verify_closure
from .live_verification import validate_evidence
from .persistent_state import StateSnapshot
from .publication_contract import ASSETS, REPOSITORY_ID, canonical, sha, require, positive, digest, validate_state
from .success_approval import verify as verify_approval


def build(closure, archive_ref, index, live, approval_bytes, trusted_approval_sha256, deployment, now):
    """The controller supplies a separately pinned, owner-reviewed import approval.

    Remote asset read-back, immutability and protected append must be established
    before calling. Output is local files, never permission to push or publish.
    """
    receipt = verify_closure(closure)
    require(receipt['kind'] == 'legacy-import', 'Genesis must import the original approved version')
    require(sha(approval_bytes) == trusted_approval_sha256, 'Independent initialization approval digest differs')
    validate_evidence(live, closure['site.zip'], now)
    require(index['schemaVersion'] == 1 and index['repositoryId'] == archive_ref['repositoryId'] == REPOSITORY_ID and
            index['releaseId'] == archive_ref['releaseId'] and index['tag'] == archive_ref['tag'] and
            sha(canonical(index)) == archive_ref['packageIndexSha256'] and
            sha(closure['candidate-receipt.json']) == archive_ref['receiptSha256'] and
            set(index['assets']) == set(ASSETS), 'Genesis archive index binding mismatch')
    positive(archive_ref['releaseId']); positive(archive_ref['indexAssetId'])
    ids = [archive_ref['indexAssetId']]
    for name in ASSETS:
        asset = index['assets'][name]; positive(asset['id']); ids.append(asset['id'])
        require(asset['sha256'] == sha(closure[name]) and asset['bytes'] == len(closure[name]), 'Genesis asset bytes differ')
    require(len(ids) == len(set(ids)), 'Duplicate remote genesis asset IDs')
    require(deployment['status'] == 'success' and deployment['rawStatus'] == 'succeed' and
            isinstance(deployment['id'], str) and deployment['id'] and
            deployment['runId'] == 38496725153 and deployment['jobId'] == 115634120612 and
            deployment['pagesArtifactId'] == 11864511360 and deployment['source'] == 'verified-original-Pages-run',
            'Original Pages evidence required; genesis never deploys')
    digest(deployment['logsSha256'])
    eb = canonical(live)
    pointer = {'generation': 0, 'publishedZipSha256': sha(closure['site.zip']),
        'receiptSha256': sha(closure['candidate-receipt.json']), 'acquisitionZipSha256': sha(closure['acquisition-state.zip']),
        'packageIndexSha256': archive_ref['packageIndexSha256'], 'archive': archive_ref,
        'frontendPinSha256': receipt['frontend']['frontendPinSha256'], 'seedZipSha256': receipt['frontend']['seedZipSha256'],
        'sourceIdentitySha256': receipt['output']['sourceIdentitySha256'], 'sourceRunId': receipt['provenance']['sourceRunId'],
        'runAttempt': receipt['provenance']['runAttempt'], 'deploymentId': deployment['id'], 'previous': None}
    record = {'schemaVersion': 1, 'key': sha(canonical({'kind':'legacy-import','archive':archive_ref})),
        'kind':'legacy-import', 'pointer':pointer, 'baseline':None, 'deployment':deployment,
        'liveEvidenceSha256':sha(eb), 'approvalSha256':trusted_approval_sha256, 'at':now.isoformat()}
    sb = canonical(record)
    state = {'schemaVersion':1,'repositoryId':REPOSITORY_ID,'stateRevision':0,'fenceCounter':0,
        'control':{'halted':False,'reason':None}, 'activeTransaction':None,
        'successfulPointer':{**pointer,'successRecordSha256':sha(sb)}}
    files = {'state.json':canonical(validate_state(state)), 'successes/g0.json':sb,
        'live-evidence/'+sha(eb)+'.json':eb, 'approvals/'+trusted_approval_sha256+'.json':approval_bytes,
        'receipts/'+pointer['receiptSha256']+'.json':closure['candidate-receipt.json'],
        'indexes/'+archive_ref['packageIndexSha256']+'.json':canonical(index)}
    verify_approval(StateSnapshot('0'*40,state,files),record,receipt,offline=False,
                    trusted_approvals={trusted_approval_sha256:approval_bytes})
    return files
