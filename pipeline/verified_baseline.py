"""Only the successful pointer selects a baseline; never latest, checkout or pending."""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from .publication_contract import require, sha, canonical
from .candidate_package import verify_closure
from . import acquisition_state as acquisition


@dataclass(frozen=True)
class VerifiedBaseline:
    state_head: str
    pointer: dict
    payload: dict
    closure: dict
    live_evidence: dict

    @property
    def binding(self):
        return {'generation': self.pointer['generation'], 'publishedZipSha256': self.pointer['publishedZipSha256'],
                'receiptSha256': self.pointer['receiptSha256'], 'acquisitionZipSha256': self.pointer['acquisitionZipSha256'],
                'stateHead': self.state_head}

    def materialize(self, destination):
        acquisition.unpack(self.closure['acquisition-state.zip'], destination)
        return Path(destination)


def _success_chain(snapshot, *, offline, trusted_approvals=None):
    current = snapshot.state['successfulPointer']
    expected = current['successRecordSha256']
    for generation in range(current['generation'], -1, -1):
        body = snapshot.files['successes/g'+str(generation)+'.json']
        require(sha(body) == expected, 'SuccessRecord chain digest mismatch')
        record = json.loads(body)
        require(record['schemaVersion'] == 1 and record['pointer']['generation'] == generation, 'Success generation mismatch')
        receipt_sha = record['pointer']['receiptSha256']
        receipt_bytes = snapshot.files['receipts/'+receipt_sha+'.json']
        require(sha(receipt_bytes) == receipt_sha, 'Historical success receipt corrupted')
        from .success_approval import verify as verify_approval
        from .publication_contract import validate_receipt
        saved_approval = verify_approval(snapshot, record, validate_receipt(json.loads(receipt_bytes)),
                        offline=offline, trusted_approvals=trusted_approvals)
        if generation and not offline:
            from .pages_artifact import validate_saved_proof
            validate_saved_proof(record.get('pagesArtifactProof'), record.get('pagesArtifactProofSha256'),
                                 json.loads(receipt_bytes), publisher_sha=saved_approval['publisher_sha'])
        if generation == current['generation']:
            require(record['pointer'] == {k: v for k, v in current.items() if k != 'successRecordSha256'}, 'Pointer/SuccessRecord differs')
        previous = record['pointer'].get('previous')
        if generation:
            require(previous['generation'] == generation-1, 'Success chain gap')
            prior = json.loads(snapshot.files['successes/g'+str(generation-1)+'.json'])
            require(previous['publishedZipSha256'] == prior['pointer']['publishedZipSha256'], 'Previous ZIP chain mismatch')
            expected = previous['successRecordSha256']
        else:
            require(previous is None and record['kind'] == 'legacy-import', 'Genesis not a verified legacy import')
    return json.loads(snapshot.files['successes/g'+str(current['generation'])+'.json'])


def load_verified_baseline(store, archive, verifier, expected_published_zip_sha256, expected_generation, *, diagnostic=False, trusted_approvals=None):
    snapshot = store.read(); state = snapshot.state; p = state['successfulPointer']
    require(p['publishedZipSha256'] == expected_published_zip_sha256 and p['generation'] == expected_generation, 'Expected successful baseline differs')
    require(diagnostic or (not state['control']['halted'] and state['activeTransaction'] is None), 'Unresolved/halted publication blocks baseline work')
    record = _success_chain(snapshot, offline=store.backend.offline and archive.backend.offline,
                            trusted_approvals=trusted_approvals)
    files, index = archive.load(p['archive'])
    r = verify_closure(files, p['receiptSha256'])
    require(sha(files['site.zip']) == p['publishedZipSha256'] and sha(files['acquisition-state.zip']) == p['acquisitionZipSha256'] and
            p['packageIndexSha256'] == p['archive']['packageIndexSha256'], 'Successful archive binding differs')
    require(p['frontendPinSha256'] == r['frontend']['frontendPinSha256'] and p['seedZipSha256'] == r['frontend']['seedZipSha256'] and
            p['sourceIdentitySha256'] == r['output']['sourceIdentitySha256'] and str(p['sourceRunId']) == str(r['provenance']['sourceRunId']) and
            p['runAttempt'] == r['provenance']['runAttempt'], 'Pointer provenance/seed mismatch')
    require(snapshot.files['receipts/'+p['receiptSha256']+'.json'] == files['candidate-receipt.json'] and
            snapshot.files['indexes/'+p['packageIndexSha256']+'.json'] == canonical(index), 'State receipt/index copy mismatch')
    evidence = snapshot.files['live-evidence/'+record['liveEvidenceSha256']+'.json']
    require(sha(evidence) == record['liveEvidenceSha256'] and json.loads(evidence)['siteZipSha256'] == p['publishedZipSha256'], 'Missing original success live evidence')
    from .live_verification import validate_evidence
    from datetime import datetime
    original_evidence = json.loads(evidence)
    validate_evidence(original_evidence, files['site.zip'], datetime.fromisoformat(original_evidence['verifiedAt']))
    require(record['deployment']['id'] == p['deploymentId'] and record['deployment']['rawStatus'] == 'succeed', 'No confirmed Pages success')
    live = verifier.verify(files['site.zip'])
    internal = acquisition.unpack(files['acquisition-state.zip'])
    return VerifiedBaseline(snapshot.head, p, json.loads(internal['market.json']), files, live)


def acquire_candidate(baseline, output, target, now, run_id, run_attempt, *, intended_slot, fetch_current=False):
    """Supported persistent-baseline entry. No checkout fallback, even when missing state."""
    require(isinstance(baseline, VerifiedBaseline), 'VerifiedBaseline required before acquisition')
    from .daily_release import target_day
    require(target_day(now, target) == target and intended_slot['targetDate'] == target and intended_slot['timezone'] == 'Asia/Taipei' and
            datetime.fromisoformat(intended_slot['startedAt']) == now and now <= datetime.fromisoformat(intended_slot['deadline']), 'Original intended slot mismatch/expired')
    import tempfile
    from .daily_release import controlled
    with tempfile.TemporaryDirectory(prefix='verified-scanner-input-') as t:
        root = baseline.materialize(Path(t)/'data')
        before = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
        try:
            return controlled(root, output, target, now, run_id, fetch_current,
                              baseline_binding=baseline.binding, run_attempt=run_attempt,intended_slot=intended_slot)
        finally:
            after = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
            require(before == after, 'Verified baseline mutated during acquisition')


def main(argv=None, *, api=None, live_verifier=None):
    """Read-only persistent baseline loader followed by explicitly requested candidate acquisition."""
    import argparse
    import os
    import tempfile
    from .common import TPE, ROOT
    from .candidate_io import candidate_destination, exclusive_lock, publish_directory, atomic_json
    from .persistent_state import StateStore, GitHubState
    from .release_archive import ReleaseArchive, GitHubReleases
    from .github_transport import GitHubAPI
    from .live_verification import LiveVerifier
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-zip-sha256', required=True); p.add_argument('--expected-generation', type=int, required=True)
    p.add_argument('--target-date', required=True); p.add_argument('--run-id', required=True); p.add_argument('--run-attempt', type=int, required=True)
    p.add_argument('--slot', required=True); p.add_argument('--deadline', required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--fetch-current', action='store_true')
    args = p.parse_args(argv); now = datetime.now(TPE)
    output = candidate_destination(ROOT/'data', args.output)
    api = api or GitHubAPI(os.environ.get('GH_TOKEN'))
    try:
        baseline = load_verified_baseline(StateStore(GitHubState(api)), ReleaseArchive(GitHubReleases(api)), live_verifier or LiveVerifier(),
                                          args.expected_zip_sha256, args.expected_generation)
        slot = {'timezone':'Asia/Taipei', 'targetDate':args.target_date, 'event':'workflow_dispatch', 'slot':args.slot,
                'deadline':args.deadline, 'startedAt':now.isoformat()}
        acquire_candidate(baseline, output, args.target_date, now, args.run_id, args.run_attempt,
                          intended_slot=slot, fetch_current=args.fetch_current)
        return 0
    except Exception as exc:
        if not output.exists():
            with exclusive_lock(output.parent/('.'+output.name+'.lock')), tempfile.TemporaryDirectory(dir=output.parent) as t:
                staged = Path(t)/'failure'; staged.mkdir()
                atomic_json(staged/'failure.json', {'error':str(exc), 'runId':args.run_id, 'runAttempt':args.run_attempt,
                    'productionUnchanged':True, 'baselineVerified':False, 'fallbackUsed':False})
                publish_directory(staged, output)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
