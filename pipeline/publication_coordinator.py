"""Durable single-publisher protocol. Offline authority cannot enable GitHub writes."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from .publication_contract import canonical, sha, require, operation_key
from .persistent_state import CASConflict
from .candidate_package import verify_closure
from .live_verification import validate_evidence
from .pages_transport import PagesRejected

_OFFLINE_SEAL = object()


@dataclass(frozen=True)
class OfflineApproval:
    """Test-only authority for local backends. No CLI/serialized equivalent."""
    kind: str
    zip_sha: str
    receipt_sha: str
    seed_sha: str
    expected_head: str
    expected_generation: int
    expected_zip: str
    expires_at: str
    reference: str
    code_sha: str
    publisher_sha: str
    seal: object


def offline_approval(kind, receipt, baseline, expires_at, reference='offline-test-owner', *, publisher_sha=None):
    return OfflineApproval(kind, receipt['output']['siteZipSha256'], sha(canonical(receipt)),
                           receipt['frontend']['seedZipSha256'], baseline.state_head,
                           baseline.pointer['generation'], baseline.pointer['publishedZipSha256'],
                           expires_at, reference, receipt['provenance']['processorCommit'],
                           publisher_sha or receipt['provenance']['processorCommit'], _OFFLINE_SEAL)


class PublicationCoordinator:
    def __init__(self, store, archive, pages, verifier, *, clock=lambda: datetime.now(timezone.utc), checkpoint=lambda _: None):
        self.store = store; self.archive = archive; self.pages = pages; self.verifier = verifier
        self.clock = clock; self.checkpoint = checkpoint
        self._owned = {}  # A restarted worker is read-only until separately reconciled/authorized.

    def _authorize(self, approval, receipt, baseline, kind):
        require(self.store.backend.offline and self.archive.backend.offline and self.pages.offline,
                'Remote authority NOT_AUTHORIZED')
        require(isinstance(approval, OfflineApproval) and approval.seal is _OFFLINE_SEAL and
                approval.kind == kind and approval.zip_sha == receipt['output']['siteZipSha256'] and
                approval.receipt_sha == sha(canonical(receipt)) and approval.seed_sha == receipt['frontend']['seedZipSha256'] and
                approval.code_sha == receipt['provenance']['processorCommit'] and
                approval.expected_head == baseline.state_head and approval.expected_generation == baseline.pointer['generation'] and
                approval.expected_zip == baseline.pointer['publishedZipSha256'] and approval.reference and
                self.clock() < datetime.fromisoformat(approval.expires_at), 'Missing/expired/exact approval mismatch')
        from .publication_contract import digest
        digest(approval.publisher_sha, 40)
        require(kind != 'publish' or approval.publisher_sha == approval.code_sha, 'Publish code differs from approved producer')
        return {**{k: v for k, v in asdict(approval).items() if k != 'seal'},
                'schemaVersion': 1, 'authorityKind': 'offline-test', 'authorizedAt': self.clock().isoformat()}

    def completed(self, key):
        snap = self.store.read()
        for n, b in snap.files.items():
            if n.startswith('successes/'):
                record = json.loads(b)
                if record['key'] == key:
                    return record
        return None

    def _transition(self, snap, tx, phase, fields=None, files=None, halt=None, finalize=None):
        key = tx['key']; fence = tx['fence']; fields = fields or {}; files = files or {}

        def mutate(s):
            sequence = s['stateRevision']+1
            event = {'schemaVersion': 1, 'key': key, 'sequence': sequence, 'phase': phase, 'fence': fence,
                     'at': self.clock().isoformat(), 'previousEventSha256': tx.get('lastEventSha256'), 'details': fields}
            eb = canonical(event); additions = {**files, 'transactions/'+key+'/'+str(sequence)+'.json': eb}
            s['stateRevision'] = sequence
            s['activeTransaction'] = {**tx, **fields, 'phase': phase, 'lastEventSha256': sha(eb)}
            if phase == 'PREPARED':
                require(not s['control']['halted'] and s['activeTransaction']['fence'] == s['fenceCounter']+1, 'Cannot reserve publisher')
                s['fenceCounter'] = fence
            if halt:
                s['control'] = {'halted': True, 'reason': halt, 'operationKey': key, 'phase': phase}
            if finalize:
                pointer, success = finalize
                s['successfulPointer'] = pointer; s['activeTransaction'] = None
                additions['successes/g'+str(pointer['generation'])+'.json'] = canonical(success)
            return s, additions
        return self.store.cas_transition(snap.head, snap.state['successfulPointer']['generation'], key,
                    None if phase == 'PREPARED' else fence, mutate)

    def prepare_publication(self, baseline, archive_ref, approval, *, kind='publish', pages_artifact_id=None, pages_artifact_run=None):
        files, index = self.archive.load(archive_ref); r = verify_closure(files)
        key = operation_key(baseline.pointer, r['output']['siteZipSha256'], r['slot']['targetDate'], kind)
        done = self.completed(key)
        if done:
            return {'completed': done, 'key': key}
        auth = self._authorize(approval, r, baseline, kind)
        artifact_proof = None
        if pages_artifact_id is not None:
            require(pages_artifact_run and pages_artifact_run['headSha'] == auth['publisher_sha'],
                    'Exact approved Pages artifact producer required')
            artifact_proof = self.pages.verify_artifact(pages_artifact_id, files['site.zip'], pages_artifact_run)
        else:
            require(self.pages.offline, 'Real Pages requires bound artifact bytes')
        snap = self.store.read(); s = snap.state
        require(snap.head == baseline.state_head and s['successfulPointer'] == baseline.pointer, 'Stale baseline state head')
        require(not s['control']['halted'] and s['activeTransaction'] is None, 'Publisher active/halted; no lease expiry unlock')
        require(kind in ('publish', 'manual-restore'), 'Unsupported publication operation')
        from .acquisition_state import unpack
        baseline_files, _ = self.archive.load(s['successfulPointer']['archive'])
        require(sha(baseline_files['site.zip']) == s['successfulPointer']['publishedZipSha256'] and
                json.loads(unpack(baseline_files['acquisition-state.zip'])['market.json']) == baseline.payload,
                'Baseline payload must match successful archived acquisition')
        if kind == 'publish':
            require(r['kind'] == 'publish' and r['baseline'] == baseline.binding, 'Candidate not from this successful baseline')
            from .daily_release import gate,target_day
            require(target_day(self.clock(),r['slot']['targetDate'])==r['slot']['targetDate'] and
                    self.clock()<=datetime.fromisoformat(r['slot']['deadline']), 'Original publication slot expired')
            payload = json.loads(unpack(files['acquisition-state.zip'])['market.json'])
            require(gate(payload, baseline.payload, r['slot']['targetDate']) == 'candidate', 'Independent publication data gate')
        self.verifier.verify(baseline.closure['site.zip'])
        tx = {'key': key, 'fence': s['fenceCounter']+1, 'phase': 'PREPARED', 'kind': kind,
              'baseline': baseline.binding, 'baselineArchive': baseline.pointer['archive'], 'archive': archive_ref,
              'candidateZipSha256': r['output']['siteZipSha256'], 'receiptSha256': sha(files['candidate-receipt.json']),
              'sourceRunId': r['provenance']['sourceRunId'], 'runAttempt': r['provenance']['runAttempt'],
              'approval': auth, 'deploymentId': None, 'pagesArtifactId': pages_artifact_id,
              'pagesArtifactProof': artifact_proof, 'pagesArtifactProofSha256': sha(canonical(artifact_proof)) if artifact_proof else None,
              'dispatchDeadline':r['slot']['deadline'] if kind=='publish' else auth['expires_at'],
              'statusReads': 0, 'preparedAt': self.clock().isoformat(), 'dispatchStartedAt': None}
        self.checkpoint('prepare.before')
        prepared = self._transition(snap, tx, 'PREPARED', files={'approvals/'+sha(canonical(auth))+'.json': canonical(auth)})
        self._owned[key] = tx['fence']
        self.checkpoint('prepare.after')
        return prepared.state['activeTransaction']

    def _active(self, key, fence, phases):
        snap = self.store.read(); s = snap.state; tx = s['activeTransaction']
        require(not s['control']['halted'] and tx and tx['key'] == key and tx['fence'] == fence and tx['phase'] in phases,
                'Halted, stale fence or invalid phase; reconcile only')
        require(s['successfulPointer']['generation'] == tx['baseline']['generation'] and
                s['successfulPointer']['publishedZipSha256'] == tx['baseline']['publishedZipSha256'], 'Baseline changed under transaction')
        return snap, tx

    def halt(self, key, fence, reason, phase='UNKNOWN'):
        try:
            snap = self.store.read(); tx = snap.state['activeTransaction']
            if not tx or tx['key'] != key or tx['fence'] != fence:
                return {'status': 'HALTED', 'reason': reason, 'stateWrite': 'conflicting writer; no rebase'}
            return self._transition(snap, tx, phase, {'error': reason}, halt=reason).state['activeTransaction']
        except Exception:
            # Existing reservation remains the durable safety barrier when state is unavailable.
            return {'status': 'UNKNOWN', 'reason': reason, 'stateWrite': 'unavailable; active reservation must be reconciled'}

    def request_pages_once(self, key, fence):
        require(self._owned.get(key) == fence, 'Restarted worker must reconcile; no automatic create')
        snap, tx = self._active(key, fence, {'PREPARED'})
        require(self.clock() < datetime.fromisoformat(tx['approval']['expires_at']), 'Approval expired before dispatch')
        require(self.clock() <= datetime.fromisoformat(tx['dispatchDeadline']), 'Original dispatch deadline expired')
        old_files, _ = self.archive.load(tx['baselineArchive'])
        self.verifier.verify(old_files['site.zip'])
        require(self.clock() <= datetime.fromisoformat(tx['dispatchDeadline']), 'Deadline crossed during baseline verification')
        self.checkpoint('request.before_intent')
        snap = self._transition(snap, tx, 'DEPLOY_REQUESTED', {'dispatchStartedAt': self.clock().isoformat()})
        tx = snap.state['activeTransaction']
        self.checkpoint('request.after_intent')
        latest, active = self._active(key, fence, {'DEPLOY_REQUESTED'})
        require(latest.head == snap.head and active['deploymentId'] is None, 'Dispatch intent changed before Pages POST')
        require(self.clock()<=datetime.fromisoformat(active['dispatchDeadline']) and
                self.clock()<datetime.fromisoformat(active['approval']['expires_at']), 'Dispatch authorization/window expired before POST')

        def persist(did):
            require(isinstance(did, str) and did, 'Missing Pages ID')
            current, active = self._active(key, fence, {'DEPLOY_REQUESTED'})
            require(active['deploymentId'] is None, 'Pages create already recorded')
            self._transition(current, active, 'DEPLOY_REQUESTED', {'deploymentId': did})
        try:
            # No create call is reachable from DEPLOY_REQUESTED on resume.
            self.pages.create_once(tx, persist)
        except PagesRejected as exc:
            try:
                self.verifier.verify(old_files['site.zip'])
            except Exception:
                return self.halt(key, fence, str(exc), 'UNKNOWN')
            return self.halt(key, fence, str(exc), 'FAILED_SAFE')
        except Exception as exc:
            return self.halt(key, fence, str(exc), 'UNKNOWN')
        return self.store.read().state['activeTransaction']

    def observe_pages(self, key, fence):
        require(self._owned.get(key) == fence, 'Restarted worker may only reconcile read-only')
        snap, tx = self._active(key, fence, {'DEPLOY_REQUESTED'})
        if tx['deploymentId'] is None:
            return self.halt(key, fence, 'Deployment ID unknown; no resubmit')
        if tx['statusReads'] >= 40 or (self.clock()-datetime.fromisoformat(tx['dispatchStartedAt'])).total_seconds() > 540:
            return self.halt(key, fence, 'Bounded Pages observation expired')
        try:
            status = self.pages.status(tx['deploymentId'])
            require(status['id'] == tx['deploymentId'], 'Pages ID mismatch')
            if status['status'] == 'success':
                return self._transition(snap, tx, 'DEPLOY_CONFIRMED', {'pagesStatus': status}).state['activeTransaction']
            if status['status'] == 'pending':
                return self._transition(snap, tx, 'DEPLOY_REQUESTED', {'statusReads': tx['statusReads']+1, 'pagesStatus': status}).state['activeTransaction']
            if status['status'] == 'failure':
                try:
                    old, _ = self.archive.load(tx['baselineArchive']); self.verifier.verify(old['site.zip'])
                    return self.halt(key, fence, 'Pages terminal failure; old live verified', 'FAILED_SAFE')
                except Exception:
                    return self.halt(key, fence, 'Failure does not prove live unchanged')
            return self.halt(key, fence, 'Unrecognized Pages status: '+str(status['rawStatus']))
        except Exception as exc:
            return self.halt(key, fence, 'Pages status unavailable: '+str(exc))

    def verify_live(self, key, fence):
        require(self._owned.get(key) == fence, 'Restarted worker may only reconcile read-only')
        snap, tx = self._active(key, fence, {'DEPLOY_CONFIRMED'})
        try:
            files, _ = self.archive.load(tx['archive']); evidence = self.verifier.verify(files['site.zip'])
            self.checkpoint('verify.after_http')
            eb = canonical(evidence)
            return self._transition(snap, tx, 'LIVE_VERIFIED', {'liveEvidenceSha256': sha(eb)},
                    files={'live-evidence/'+sha(eb)+'.json': eb}).state['activeTransaction']
        except Exception as exc:
            return self.halt(key, fence, 'Candidate live verification failed: '+str(exc), 'HALTED')

    def finalize_success(self, key, fence, expected_current):
        done = self.completed(key)
        if done:
            return done
        require(self._owned.get(key) == fence, 'Restarted worker needs separately authorized finalize plan')
        snap, tx = self._active(key, fence, {'LIVE_VERIFIED'})
        require(snap.head == expected_current, 'Final exact expected state head required')
        try:
            require(self.clock() < datetime.fromisoformat(tx['approval']['expires_at']), 'Approval expired before finalize')
            status = self.pages.status(tx['deploymentId'])
            require(status['id'] == tx['deploymentId'] and status['status'] == 'success' and status['rawStatus'] == 'succeed', 'Pages no longer confirmed')
            files, index = self.archive.load(tx['archive']); r = verify_closure(files)
            evidence = self.verifier.verify(files['site.zip']); validate_evidence(evidence, files['site.zip'], self.clock())
            self.checkpoint('finalize.after_http')
            eb = canonical(evidence); old = snap.state['successfulPointer']
            pointer = {'generation': old['generation']+1, 'publishedZipSha256': sha(files['site.zip']),
                'receiptSha256': sha(files['candidate-receipt.json']), 'acquisitionZipSha256': sha(files['acquisition-state.zip']),
                'packageIndexSha256': tx['archive']['packageIndexSha256'], 'archive': tx['archive'],
                'frontendPinSha256': r['frontend']['frontendPinSha256'], 'seedZipSha256': r['frontend']['seedZipSha256'],
                'sourceIdentitySha256': r['output']['sourceIdentitySha256'], 'sourceRunId': r['provenance']['sourceRunId'],
                'runAttempt': r['provenance']['runAttempt'], 'deploymentId': tx['deploymentId'],
                'previous': {k: old[k] for k in ('generation', 'publishedZipSha256', 'successRecordSha256')}}
            success = {'schemaVersion': 1, 'key': key, 'kind': tx['kind'], 'pointer': pointer,
                       'baseline': tx['baseline'],
                       'pagesArtifactProof': tx['pagesArtifactProof'], 'pagesArtifactProofSha256': tx['pagesArtifactProofSha256'],
                       'deployment': status, 'liveEvidenceSha256': sha(eb), 'approvalSha256': sha(canonical(tx['approval'])),
                       'at': self.clock().isoformat(), 'rollbackOf': old['generation'] if tx['kind'] == 'manual-restore' else None}
            success_body = canonical(success); pointer = {**pointer, 'successRecordSha256': sha(success_body)}
            self.checkpoint('finalize.before_cas')
            self._transition(snap, tx, 'SUCCESS_RECORDED', files={
                'live-evidence/'+sha(eb)+'.json': eb, 'receipts/'+sha(files['candidate-receipt.json'])+'.json': files['candidate-receipt.json'],
                'indexes/'+tx['archive']['packageIndexSha256']+'.json': canonical(index)}, finalize=(pointer, success))
            self.checkpoint('finalize.after_cas')
            return success
        except Exception as exc:
            return self.halt(key, fence, 'Final success not safely recorded: '+str(exc), 'HALTED')
