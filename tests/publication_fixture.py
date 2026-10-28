"""Clearly synthetic, local-only publications; never evidence of a real deployment."""
import copy
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit
from pipeline.common import ROOT, TPE, read_json, write_json
from pipeline.publication_contract import canonical, sha, zip_bytes
from pipeline.observation_release import check
from pipeline.daily_release import project, bundle, controlled
from pipeline.package_daily import package
from pipeline.candidate_package import legacy_import_plan, prepare_candidate
from pipeline.release_archive import FilesystemReleases, ReleaseArchive
from pipeline.persistent_state import LocalGitState, StateStore
from pipeline.live_verification import LiveVerifier, BASE_URL
from pipeline.verified_baseline import load_verified_baseline
from pipeline.publication_coordinator import PublicationCoordinator, offline_approval
from pipeline.pages_transport import FakePages

NOW = datetime(2026, 10, 14, 20, tzinfo=TPE)
EXPIRES = '2026-10-14T23:59:59+08:00'


class LiveSite:
    def __init__(self, zip_body):
        self.set(zip_body); self.calls = []; self.inject = None

    def set(self, zip_body):
        from pipeline.publication_contract import site_files
        self.body = zip_body; self.files = site_files(zip_body)

    def fetch(self, url, timeout):
        self.calls.append(url)
        path = urlsplit(url).path.removeprefix('/tw-market-scanner/')
        if self.inject:
            result = self.inject(path, len(self.calls))
            if result is not None:
                return result
        return {'status': 200, 'url': url, 'body': self.files[path],
                'headers': {'Cache-Control': 'max-age=0', 'Set-Cookie': 'DO-NOT-RECORD', 'Authorization': 'DO-NOT-RECORD'}}


def verifier(live):
    return LiveVerifier(live.fetch, clock=lambda: NOW, sleep=lambda _: None)


def bootstrap_files(closure, ref, index, live):
    r = json.loads(closure['candidate-receipt.json']); evidence = verifier(live).verify(closure['site.zip'])
    eb = canonical(evidence)
    pointer = {'generation': 0, 'publishedZipSha256': sha(closure['site.zip']), 'receiptSha256': sha(closure['candidate-receipt.json']),
        'acquisitionZipSha256': sha(closure['acquisition-state.zip']), 'packageIndexSha256': ref['packageIndexSha256'],
        'archive': ref, 'frontendPinSha256': r['frontend']['frontendPinSha256'], 'seedZipSha256': r['frontend']['seedZipSha256'],
        'sourceIdentitySha256': r['output']['sourceIdentitySha256'], 'sourceRunId': r['provenance']['sourceRunId'],
        'runAttempt': r['provenance']['runAttempt'], 'deploymentId': 'offline-genesis', 'previous': None}
    approval = {'schemaVersion': 1, 'authorityKind': 'offline-test', 'kind': 'legacy-import',
        'zip_sha': sha(closure['site.zip']), 'receipt_sha': sha(closure['candidate-receipt.json']),
        'seed_sha': r['frontend']['seedZipSha256'], 'code_sha': r['provenance']['processorCommit'],
        'publisher_sha': r['provenance']['processorCommit'],
        'deployment_id': 'offline-genesis',
        'expected_head': None, 'expected_generation': None, 'expected_zip': None,
        'authorizedAt': NOW.isoformat(), 'expires_at': EXPIRES, 'reference': 'offline-fixture-owner'}
    ab = canonical(approval)
    success = {'schemaVersion': 1, 'key': sha(b'offline-genesis'), 'kind': 'legacy-import', 'pointer': pointer,
               'baseline': None, 'at': NOW.isoformat(), 'approvalSha256': sha(ab),
               'deployment': {'id': 'offline-genesis', 'rawStatus': 'succeed', 'status': 'success'}, 'liveEvidenceSha256': sha(eb)}
    sb = canonical(success); pointer = {**pointer, 'successRecordSha256': sha(sb)}
    state = {'schemaVersion': 1, 'repositoryId': 1412557806, 'stateRevision': 0, 'fenceCounter': 0,
             'control': {'halted': False, 'reason': None}, 'successfulPointer': pointer, 'activeTransaction': None}
    return {'state.json': canonical(state), 'successes/g0.json': sb, 'live-evidence/'+sha(eb)+'.json': eb,
            'approvals/'+sha(ab)+'.json': ab,
            'receipts/'+sha(closure['candidate-receipt.json'])+'.json': closure['candidate-receipt.json'],
            'indexes/'+ref['packageIndexSha256']+'.json': canonical(index)}


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        self.env_patch = patch.dict('os.environ', {'RC_COMMIT_SHA': self.commit}); self.env_patch.start()
        raw = (ROOT/'data/market.json').read_bytes()
        body, report = check(raw, now=NOW)
        static = {'index.html': b'legacy fixture UI', '.nojekyll': b'', 'assets/index.js': b'legacy fixed formula fixture'}
        manifest = {**report, 'candidateCommit': self.commit, 'assets': {n: sha(b) for n, b in {**static, 'market.json': body}.items()}}
        self.old_site = zip_bytes({**static, 'market.json': body, 'release-manifest.json': canonical(manifest)})
        # Pins are scoped to this fixture only; actual original RC verification is separate.
        self.pins = patch.multiple('pipeline.candidate_package', LEGACY_ZIP=sha(self.old_site), LEGACY_COMMIT=self.commit, LEGACY_DATA=sha(body))
        self.pins.start()
        provenance = self.provenance('900')
        self.old = legacy_import_plan(self.old_site, ROOT/'data', provenance, self.slot('2026-10-13'))
        self.backend = FilesystemReleases(self.root/'archives'); self.archive = ReleaseArchive(self.backend)
        self.old_ref = self.archive.archive_candidate(self.old)
        self.live = LiveSite(self.old_site)
        bare = self.root/'state.git'; subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        self.state_backend = LocalGitState(bare); self.store = StateStore(self.state_backend)
        self.state_backend.initialize_offline(bootstrap_files(self.old, self.old_ref, self.archive.load(self.old_ref)[1], self.live))
        self.baseline = load_verified_baseline(self.store, self.archive, verifier(self.live), sha(self.old_site), 0)
        # Exercise controlled acquisition with six mocked latest adapters, never HTTP.
        snaps = {}
        for module in ('calendar', 'companies', 'quotes', 'tpexCompanies', 'tpexQuotes', 'tpexInstitutional'):
            source = self.baseline.payload['sources'][module]
            snap = read_json(ROOT/'data/raw'/f"{module}_{source['asOf']}.json")
            snap = copy.deepcopy(snap)
            if module in ('quotes', 'tpexQuotes', 'tpexInstitutional'):
                snap['date'] = '2026-10-14'
                for row in snap['rows']:
                    row['date'] = '2026-10-14'
                snap['sha256'] = sha(canonical(snap['rows']))
            snaps[module] = snap
        from pipeline.run import SOURCES
        by_url = {SOURCES[m][1]: m for m in snaps}
        def get(url, params=None):
            m = by_url[url]; return {}, snaps[m]['sha256'], url
        from pipeline.current_csv import URL
        adapters = {m: (lambda raw, m=m: (snaps[m]['date'], snaps[m]['rows'])) for m in snaps}
        candidate = self.root/'candidate'
        with patch('pipeline.daily.PARSERS', adapters), patch('pipeline.run.get_json', side_effect=get), patch('pipeline.daily.fetch_twse_csv', return_value=({}, snaps['quotes']['sha256'], URL)):
            self.baseline.materialize(self.root/'input')
            controlled(self.root/'input', candidate, '2026-10-14', NOW, '1001', True,
                       baseline_binding=self.baseline.binding, run_attempt=1,intended_slot=self.slot('2026-10-14'))
        seed_dir = self.root/'seed'; seed_dir.mkdir()
        (seed_dir/'index.html').write_bytes(b'daily fixed fixture UI'); (seed_dir/'.nojekyll').write_bytes(b'')
        write_json(seed_dir/'frontend-pin.json', {'frontendId': 'observation-daily-v1', 'assets':
            {n: sha((seed_dir/n).read_bytes()) for n in ('index.html', '.nojekyll')}})
        projected, seed_report = project(self.baseline.payload, '900', NOW)
        self.seed_path = self.root/'seed.zip'; bundle(projected, seed_report, seed_dir, self.seed_path)
        self.seed = self.seed_path.read_bytes()
        package(candidate, self.seed_path, sha(self.seed), self.root/'package',baseline=self.baseline,
                slot=self.slot('2026-10-14'),provenance=self.provenance('1001'))
        from pipeline.publication_contract import ASSETS
        self.new = {n:(self.root/'package'/n).read_bytes() for n in ASSETS}
        self.new_ref = self.archive.archive_candidate(self.new)

    def provenance(self, run):
        return {'sourceRunId': run, 'runAttempt': 1, 'workflowPath': '.github/workflows/ci.yml' if run == '900' else '.github/workflows/update-data.yml',
                'status': 'completed', 'conclusion': 'success', 'codeSha': self.commit, 'processorCommit': self.commit}

    def slot(self, target):
        return {'timezone': 'Asia/Taipei', 'targetDate': target, 'event': 'offline-fixture', 'slot': 'fixture-1830',
                'startedAt': NOW.isoformat(), 'deadline': EXPIRES}

    def close(self):
        self.pins.stop(); self.env_patch.stop(); self.tmp.cleanup()

    def environment(self, directory):
        root = Path(directory)
        shutil.copytree(self.root/'archives', root/'archives')
        shutil.copytree(self.root/'state.git', root/'state.git')
        live = LiveSite(self.old_site); pages = FakePages()
        archive = ReleaseArchive(FilesystemReleases(root/'archives')); store = StateStore(LocalGitState(root/'state.git'))
        baseline = load_verified_baseline(store, archive, verifier(live), sha(self.old_site), 0)
        coordinator = PublicationCoordinator(store, archive, pages, verifier(live), clock=lambda: NOW)
        return coordinator, baseline, live


def advance_to_verified(coordinator, baseline, archive_ref, live):
    files, _ = coordinator.archive.load(archive_ref); r = json.loads(files['candidate-receipt.json'])
    approval = offline_approval('publish', r, baseline, EXPIRES)
    tx = coordinator.prepare_publication(baseline, archive_ref, approval)
    coordinator.pages.on_create = lambda _: live.set(files['site.zip'])
    coordinator.request_pages_once(tx['key'], tx['fence'])
    coordinator.observe_pages(tx['key'], tx['fence'])
    coordinator.verify_live(tx['key'], tx['fence'])
    return tx
