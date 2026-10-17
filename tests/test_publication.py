"""4C-2A fault matrix, real bare-Git races and wholly offline publication recovery."""
import base64
import copy
from dataclasses import replace
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
import zipfile
from pipeline.common import ROOT, TPE, get_json
from pipeline.publication_contract import canonical, sha, read_zip, zip_bytes, require, site_files, validate_receipt
from pipeline.acquisition_state import unpack, pack
from pipeline.candidate_package import verify_closure, prepare_candidate, legacy_import_plan
from pipeline.release_archive import ReleaseArchive, FilesystemReleases, GitHubReleases
from pipeline.persistent_state import StateStore, LocalGitState, GitHubState, CASConflict
from pipeline.verified_baseline import load_verified_baseline
from pipeline.publication_coordinator import PublicationCoordinator, offline_approval
from pipeline.reconcile_publication import reconcile, restore_verified_version
from pipeline.pages_transport import GitHubPages, PagesRejected
from pipeline.live_verification import LiveVerifier, BASE_URL
from pipeline.daily_release import gate, target_day
from tests.publication_fixture import Fixture, LiveSite, verifier, NOW, EXPIRES, advance_to_verified


def cases(*ids):
    def decorate(fn):
        fn.matrix_ids = ids
        return fn
    return decorate


class Crash(BaseException):
    pass


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = patch('socket.create_connection', side_effect=AssertionError('OFFLINE: no real network'))
        cls.network_spy = cls.network.start()
        try:
            cls.fixture = Fixture()
        except BaseException:
            cls.network.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.fixture.close()
            if cls.network_spy.call_count:
                raise AssertionError('A supposedly offline test attempted network')
        finally:
            cls.network.stop()

    def environment(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        return self.fixture.environment(t.name)

    def approval(self, b, closure=None, kind='publish'):
        r = json.loads((closure or self.fixture.new)['candidate-receipt.json'])
        return offline_approval(kind, r, b, EXPIRES)

    def prepare(self, c, b):
        return c.prepare_publication(b, self.fixture.new_ref, self.approval(b))

    def finish(self, c, b, live):
        tx = advance_to_verified(c, b, self.fixture.new_ref, live)
        result = c.finalize_success(tx['key'], tx['fence'], c.store.read().head)
        self.assertEqual(result['kind'], 'publish')
        return tx

    def assert_pointer(self, c, expected):
        self.assertEqual(c.store.read().state['successfulPointer'], expected)

    @cases('B02', 'B05', 'P01', 'P08')
    def test_success_only_after_pages_and_full_live_then_idempotent(self):
        c, b, live = self.environment()
        # A newer immutable Release exists, but only g0 is successful.
        loaded = load_verified_baseline(c.store, c.archive, verifier(live), sha(self.fixture.old_site), 0)
        self.assertEqual(loaded.payload['asOf'], '2026-10-13')
        tx = advance_to_verified(c, b, self.fixture.new_ref, live)
        self.assert_pointer(c, b.pointer)
        result = c.finalize_success(tx['key'], tx['fence'], c.store.read().head)
        self.assertEqual(c.store.read().state['successfulPointer']['generation'], 1)
        self.assertIsNone(c.store.read().state['activeTransaction'])
        self.assertEqual(len(c.pages.creates), 1)
        h = c.store.read().head
        self.assertEqual(c.finalize_success(tx['key'], tx['fence'], h), result)
        self.assertIn('completed', c.prepare_publication(b, self.fixture.new_ref, self.approval(b)))
        self.assertEqual(c.store.read().head, h); self.assertEqual(len(c.pages.creates), 1)
        # Forbid reading checkout data while restoring solely from archived state.
        original = Path.read_bytes
        def no_checkout(path):
            if path.is_relative_to(ROOT/'data'):
                raise AssertionError('Fixture fallback')
            return original(path)
        with patch.object(Path, 'read_bytes', no_checkout), tempfile.TemporaryDirectory() as t:
            new = load_verified_baseline(c.store, c.archive, verifier(live), sha(self.fixture.new['site.zip']), 1)
            root = new.materialize(Path(t)/'standalone-input')
            self.assertEqual((root/'market.json').read_bytes(), unpack(self.fixture.new['acquisition-state.zip'])['market.json'])
            self.assertEqual(new.payload['asOf'], '2026-10-14')

    @cases('B01')
    def test_missing_state_success_archive_receipt_or_source_never_falls_back(self):
        for missing in ('state.json', 'successes/g0.json', 'source', 'receipt', 'seed'):
            c, b, live = self.environment(); before = b.pointer
            with self.subTest(missing=missing), patch('pipeline.daily.run_daily') as finance:
                if missing in ('state.json', 'successes/g0.json'):
                    original = c.store.backend.files
                    c.store.backend.files = lambda h, n=missing: {k: v for k, v in original(h).items() if k != n}
                else:
                    original = c.archive.load
                    def broken(ref, kind=missing):
                        files, index = original(ref)
                        key = {'source': 'acquisition-state.zip', 'receipt': 'candidate-receipt.json', 'seed': 'supporting-material.zip'}[kind]
                        files.pop(key)
                        return files, index
                    c.archive.load = broken
                with self.assertRaises((ValueError, KeyError)):
                    load_verified_baseline(c.store, c.archive, verifier(live), before['publishedZipSha256'], 0)
                finance.assert_not_called(); self.assertEqual(c.pages.creates, [])

    @cases('B03', 'B04')
    def test_corrupt_closure_and_cross_attempt_code_bindings(self):
        for name in self.fixture.new:
            files = dict(self.fixture.new); files[name] += b'corruption'
            with self.subTest(name=name), self.assertRaises((ValueError, KeyError, zipfile.BadZipFile)):
                verify_closure(files)
        for key, value in [('runAttempt', 2), ('processorCommit', 'a'*40)]:
            files = dict(self.fixture.new); r = json.loads(files['candidate-receipt.json'])
            r['provenance'][key] = value; files['candidate-receipt.json'] = canonical(r)
            with self.assertRaises(ValueError):
                verify_closure(files)

    @cases('B06')
    def test_legacy_correct_zip_wrong_input_is_blocked_without_genesis(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)/'input'; shutil.copytree(ROOT/'data', root)
            p = json.loads((root/'market.json').read_bytes()); p['stocks'][0]['name'] += 'tamper'
            (root/'market.json').write_bytes(canonical(p))
            with self.assertRaises(ValueError):
                legacy_import_plan(self.fixture.old_site, root, self.fixture.provenance('900'), self.fixture.slot('2026-10-13'))
            self.assertFalse((Path(t)/'state.json').exists())

    @cases('B07', 'B08', 'A05')
    def test_complete_state_survives_temp_cleanup_and_distinguishes_response_digest(self):
        files = unpack(self.fixture.new['acquisition-state.zip'])
        self.assertEqual(json.loads(files['market.json'])['asOf'], '2026-10-14')
        raw = read_zip(self.fixture.new['acquisition-state.zip'], lambda _: True)
        inv = json.loads(raw['inventory.json']); name = next(n for n in inv['files'] if n.startswith('raw/'))
        inv['files'][name]['responseSha256'] = inv['files'][name]['parsedSnapshotFileSha256']
        raw['inventory.json'] = canonical(inv)
        with self.assertRaises(ValueError):
            unpack(zip_bytes(raw))
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)/'input'; unpack(self.fixture.new['acquisition-state.zip'], root)
            roster = next((root/'raw').glob('companies_*.json'))
            s = json.loads(roster.read_bytes()); s['rows'][0]['contactEmail'] = 'not-public@example.invalid'; roster.write_bytes(canonical(s))
            with self.assertRaises(ValueError):
                pack(root)
            (root/'history').mkdir(); (root/'history/unapproved.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                pack(root)

    @cases('A01')
    def test_every_release_mutation_before_and_after_crash_has_no_usable_partial_archive(self):
        points = ['release.create'] + ['release.upload.'+n for n in (*self.fixture.new.keys(), 'package-index.json')] + ['release.freeze']
        for point in points:
            for edge in ('before', 'after'):
                with self.subTest(point=point, edge=edge), tempfile.TemporaryDirectory() as t:
                    hit = point+'.'+edge
                    def inject(p):
                        if p == hit:
                            raise Crash(hit)
                    backend = FilesystemReleases(t, inject)
                    with self.assertRaises(Crash):
                        ReleaseArchive(backend).archive_candidate(self.fixture.new)
                    self.assertEqual(self.fixture.store.read().state['successfulPointer'], self.fixture.baseline.pointer)

    @cases('A01', 'A02', 'A03')
    def test_lost_archive_responses_reconcile_exact_bytes_and_never_clobber(self):
        with tempfile.TemporaryDirectory() as t:
            fired = set()
            def lost(p):
                if p.endswith('.after') and p not in fired:
                    fired.add(p); raise TimeoutError('accepted, response lost')
            archive = ReleaseArchive(FilesystemReleases(t, lost))
            ref = archive.archive_candidate(self.fixture.new)
            self.assertEqual(archive.load(ref)[0], self.fixture.new)
            self.assertEqual(archive.archive_candidate(self.fixture.new), ref)
            metadata = archive.backend.get(ref['releaseId'])
            for change in ({'immutable': False}, {'tag_name': 'wrong'}):
                changed = {**metadata, **change}
                with patch.object(archive.backend, 'get', return_value=changed), self.assertRaises(ValueError):
                    archive.load(ref)
            meta = copy.deepcopy(metadata); meta['assets'][0]['state'] = 'starter'
            with patch.object(archive.backend, 'get', return_value=meta), self.assertRaises(ValueError):
                archive.load(ref)
            meta = copy.deepcopy(metadata); meta['assets'][0]['digest'] = 'sha256:'+'0'*64
            with patch.object(archive.backend, 'get', return_value=meta), self.assertRaises(ValueError):
                archive.archive_candidate(self.fixture.new)

    @cases('A04', 'W02')
    def test_zip_safety_and_frozen_code_reject_before_extraction(self):
        for name, mode in [('../escape.json', stat.S_IFREG), ('raw/link.json', stat.S_IFLNK), ('a.py', stat.S_IFREG), ('pipe', stat.S_IFIFO)]:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as z:
                i = zipfile.ZipInfo(name); i.external_attr = (mode|0o644) << 16; z.writestr(i, b'bad')
            with self.subTest(name=name), self.assertRaises(ValueError):
                unpack(buffer.getvalue())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('market.json', b'{}')
            with self.assertWarns(UserWarning): z.writestr('market.json', b'{}')
        with self.assertRaises(ValueError): unpack(buffer.getvalue())
        with self.assertRaises(ValueError): read_zip(zip_bytes({'market.json': b'large'}), lambda _: True, expanded=1)
        with self.assertRaises(ValueError): read_zip(zip_bytes({'market.json': b'large'}), lambda _: True, compressed=1)
        files = dict(self.fixture.new); r = json.loads(files['candidate-receipt.json']); r['codeInventory']['pipeline/research.py'] = '0'*64
        files['candidate-receipt.json'] = canonical(r)
        with self.assertRaises(ValueError): verify_closure(files)

    @cases('C01', 'C02')
    def test_two_independent_processes_compete_real_bare_git_nonforce(self):
        c, b, _ = self.environment(); backend = c.store.backend; h = c.store.read().head
        worker = """import sys,json
from pipeline.persistent_state import LocalGitState,CASConflict
from pipeline.publication_contract import canonical
b=LocalGitState(sys.argv[1]); h=sys.argv[2]; s=json.loads(b.files(h)['state.json'])
s['stateRevision']+=1;s['control']['reason']=sys.argv[3]
child=b.child(h,{'state.json':canonical(s)},'different-operation-'+sys.argv[3])
print(child,flush=True);sys.stdin.readline()
try:b.advance(h,child)
except CASConflict:sys.exit(3)
"""
        workers = [subprocess.Popen([sys.executable, '-c', worker, str(backend.path), h, x], cwd=ROOT,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for x in ('a', 'b')]
        try:
            children = [p.stdout.readline().strip() for p in workers]
            self.assertNotEqual(children[0], children[1])
            for p in workers: p.stdin.write('go\n'); p.stdin.flush()
            outcomes = [p.wait(timeout=30) for p in workers]
            self.assertEqual(sorted(outcomes), [0, 3])
            self.assertIn(backend.head(), children)
            winner = backend.head(); backend.advance(h, winner)  # identical C is idempotent
            with self.assertRaises(ValueError): backend.advance(h, winner, force=True)
            with self.assertRaises(ValueError): backend.advance(winner, winner)
            self.assert_pointer(c, b.pointer)
        finally:
            for p in workers:
                if p.poll() is None: p.kill(); p.wait()
                p.stdin.close(); p.stdout.close(); p.stderr.close()

    @cases('C03', 'P08')
    def test_state_write_accepted_response_lost_and_success_after_crash(self):
        c, b, live = self.environment(); fired = []
        def lost(p):
            if p == 'state.ref.after' and not fired:
                fired.append(p); raise TimeoutError('lost state ack')
        c.store.backend.checkpoint = lost
        tx = self.prepare(c, b); self.assertEqual(c.store.read().state['stateRevision'], 1)
        c.pages.on_create = lambda _: live.set(self.fixture.new['site.zip'])
        c.request_pages_once(tx['key'], tx['fence']); c.observe_pages(tx['key'], tx['fence']); c.verify_live(tx['key'], tx['fence'])
        def crash(p):
            if p == 'finalize.after_cas': raise Crash(p)
        c.checkpoint = crash
        with self.assertRaises(Crash): c.finalize_success(tx['key'], tx['fence'], c.store.read().head)
        h = c.store.read().head
        self.assertEqual(c.finalize_success(tx['key'], tx['fence'], h)['pointer']['generation'], 1)
        self.assertEqual(c.store.read().head, h); self.assertEqual(len(c.pages.creates), 1)

    @cases('C04', 'C05', 'P04', 'R05')
    def test_reservation_survives_runner_crash_and_cannot_expire_or_rollback(self):
        for point in ('prepare.after', 'request.after_intent'):
            c, b, live = self.environment()
            def crash(p):
                if p == point: raise Crash(p)
            c.checkpoint = crash
            if point == 'prepare.after':
                with self.assertRaises(Crash): self.prepare(c, b)
            else:
                tx = self.prepare(c, b)
                with self.assertRaises(Crash): c.request_pages_once(tx['key'], tx['fence'])
            saved = c.store.read(); active = saved.state['activeTransaction']
            restarted = PublicationCoordinator(StateStore(LocalGitState(c.store.backend.path)), c.archive, c.pages, verifier(live), clock=lambda: NOW+timedelta(days=10))
            with self.assertRaises(ValueError): self.prepare(restarted, b)
            with self.assertRaises(ValueError): restarted.request_pages_once(active['key'], active['fence']+1)
            with self.assertRaises(ValueError): restore_verified_version(restarted, b, self.fixture.old_ref)
            self.assertEqual(restarted.store.read().head, saved.head); self.assertEqual(c.pages.creates, [])
            self.assert_pointer(c, b.pointer)

    @cases('P02')
    def test_explicit_refusal_and_terminal_failure_require_old_live_for_failed_safe(self):
        for mode in ('rejected', 'failed'):
            c, b, live = self.environment(); tx = self.prepare(c, b)
            if mode == 'rejected':
                def reject(p):
                    if p == 'pages.create.before': raise PagesRejected('explicit rejection')
                c.pages.checkpoint = reject
                result = c.request_pages_once(tx['key'], tx['fence'])
            else:
                c.request_pages_once(tx['key'], tx['fence'])
                c.pages.statuses[c.store.read().state['activeTransaction']['deploymentId']] = 'failed'
                result = c.observe_pages(tx['key'], tx['fence'])
            self.assertEqual(result['phase'], 'FAILED_SAFE'); self.assert_pointer(c, b.pointer)
            self.assertTrue(c.store.read().state['control']['halted'])

    @cases('C03', 'P04', 'P07', 'P09')
    def test_each_state_transition_before_after_durable_write_crash(self):
        # Six durable transitions: reserve, intent, ID, confirmed, live, success.
        for transition_number in range(6):
            for boundary in ('state.child.before', 'state.child.after', 'state.ref.before', 'state.ref.after'):
                with self.subTest(transition=transition_number, boundary=boundary):
                    c, b, live = self.environment(); count = 0
                    def inject(point):
                        nonlocal count
                        if point == boundary:
                            if count == transition_number: raise Crash(point)
                            count += 1
                    c.store.backend.checkpoint = inject
                    with self.assertRaises(Crash):
                        tx = advance_to_verified(c, b, self.fixture.new_ref, live)
                        c.finalize_success(tx['key'], tx['fence'], c.store.read().head)
                    saved = StateStore(LocalGitState(c.store.backend.path)).read()
                    p = saved.state['successfulPointer']
                    if transition_number == 5 and boundary == 'state.ref.after':
                        self.assertEqual(p['generation'], 1)
                        self.assertIn('successes/g1.json', saved.files)
                    else:
                        self.assertEqual(p, b.pointer)
                    self.assertLessEqual(len(c.pages.creates), 1)
                    restarted = PublicationCoordinator(StateStore(LocalGitState(c.store.backend.path)), c.archive, c.pages, verifier(live), clock=lambda: NOW)
                    if saved.state['activeTransaction']:
                        active = saved.state['activeTransaction']
                        with self.assertRaises(ValueError): restarted.request_pages_once(active['key'], active['fence'])
                    self.assertEqual(unpack(self.fixture.old['acquisition-state.zip']), unpack(b.closure['acquisition-state.zip']))

    @cases('P03', 'P04', 'P05')
    def test_accepted_create_lost_id_and_bad_status_never_repeat_post(self):
        c, b, live = self.environment(); tx = self.prepare(c, b)
        def lost(p):
            if p == 'pages.create.after': raise TimeoutError('accepted but ID lost')
        c.pages.checkpoint = lost; c.pages.on_create = lambda _: live.set(self.fixture.new['site.zip'])
        result = c.request_pages_once(tx['key'], tx['fence'])
        self.assertEqual(result['phase'], 'UNKNOWN'); self.assertEqual(len(c.pages.creates), 1)
        h = c.store.read().head
        for _ in range(2):
            with self.assertRaises(ValueError): c.request_pages_once(tx['key'], tx['fence'])
        plan = reconcile(c); self.assertEqual(plan['mode'], 'read-only'); self.assertTrue(plan['missingEvidence'])
        self.assertEqual(c.store.read().head, h); self.assertEqual(len(c.pages.creates), 1); self.assert_pointer(c, b.pointer)
        for raw in ('unknown-new-status', 403, 404, 429, 500):
            c, b, live = self.environment(); tx = self.prepare(c, b); c.request_pages_once(tx['key'], tx['fence'])
            did = c.store.read().state['activeTransaction']['deploymentId']
            if isinstance(raw, int): c.pages.status = Mock(side_effect=HTTPError('https://api.github.com/', raw, 'blocked', {}, None))
            else: c.pages.statuses[did] = raw
            self.assertEqual(c.observe_pages(tx['key'], tx['fence'])['phase'], 'UNKNOWN')
            self.assertEqual(len(c.pages.creates), 1); self.assert_pointer(c, b.pointer)

    @cases('P06', 'L01', 'L02', 'L03', 'L04', 'L05')
    def test_live_two_round_manifest_hashes_origin_failures_and_nojekyll_exception(self):
        c, b, live = self.environment(); tx = self.prepare(c, b); c.request_pages_once(tx['key'], tx['fence']); c.observe_pages(tx['key'], tx['fence'])
        self.assertEqual(c.verify_live(tx['key'], tx['fence'])['phase'], 'HALTED'); self.assert_pointer(c, b.pointer)
        for mode in ('manifest-after', 'redirect', 'timeout', '404', 'mixed'):
            live = LiveSite(self.fixture.new['site.zip'])
            def inject(path, count):
                response = {'status': 200, 'url': BASE_URL+path, 'body': live.files[path], 'headers': {}}
                if mode == 'manifest-after' and count > 2 and path == 'release-manifest.json': response['body'] += b' '
                if mode == 'redirect': response['url'] = 'https://other.example/'+path
                if mode == 'timeout': raise TimeoutError('bounded request')
                if mode == '404': response['status'] = 404
                if mode == 'mixed' and path == 'index.html': response['body'] += b'changed UI'
                return response
            live.inject = inject
            with self.subTest(mode=mode), self.assertRaises((ValueError, TimeoutError)):
                verifier(live).verify(self.fixture.new['site.zip'])
        live = LiveSite(self.fixture.new['site.zip']); evidence = verifier(live).verify(live.body)
        self.assertEqual(len(evidence['rounds']), 2)
        self.assertFalse(any('.nojekyll' in u for u in live.calls))
        self.assertNotIn('DO-NOT-RECORD', json.dumps(evidence))
        files = dict(self.fixture.new); site = site_files(files['site.zip']); site['index.html'] += b'1'
        m = json.loads(site['release-manifest.json']); m['assets']['index.html'] = sha(site['index.html']); site['release-manifest.json'] = canonical(m)
        files['site.zip'] = zip_bytes(site); r = json.loads(files['candidate-receipt.json']); r['output']['siteZipSha256'] = sha(files['site.zip']); r['output']['manifestSha256'] = sha(site['release-manifest.json']); files['candidate-receipt.json'] = canonical(r)
        with self.assertRaises(ValueError): verify_closure(files)

    @cases('P07', 'P09')
    def test_live_changed_pointer_old_crash_reconcile_and_final_cas_conflict(self):
        for mode in ('crash', 'conflict'):
            c, b, live = self.environment(); tx = advance_to_verified(c, b, self.fixture.new_ref, live)
            def inject(p):
                if p == 'finalize.after_http':
                    if mode == 'crash': raise Crash(p)
                    snap = c.store.read()
                    def other(s):
                        s['stateRevision'] += 1; return s, {}
                    c.store.cas_transition(snap.head, 0, tx['key'], tx['fence'], other)
            c.checkpoint = inject
            if mode == 'crash':
                with self.assertRaises(Crash): c.finalize_success(tx['key'], tx['fence'], c.store.read().head)
                h = c.store.read().head; plan = reconcile(c)
                self.assertTrue(any('finalize-existing-no-deploy' in x for x in plan['actions'])); self.assertEqual(c.store.read().head, h)
            else:
                self.assertEqual(c.finalize_success(tx['key'], tx['fence'], c.store.read().head)['phase'], 'HALTED')
            self.assert_pointer(c, b.pointer); self.assertEqual(len(c.pages.creates), 1)

    @cases('R01', 'R02', 'R03', 'R04')
    def test_complete_old_zip_restore_has_separate_exact_approval_and_new_generation(self):
        c, b, live = self.environment(); self.finish(c, b, live)
        current = load_verified_baseline(c.store, c.archive, verifier(live), sha(self.fixture.new['site.zip']), 1)
        h = c.store.read().head
        plan = restore_verified_version(c, current, self.fixture.old_ref)
        self.assertEqual(plan['mode'], 'restore-plan'); self.assertEqual(c.store.read().head, h); self.assertEqual(len(c.pages.creates), 1)
        approval = self.approval(current, self.fixture.old, 'manual-restore')
        for bad in (replace(approval, expires_at='2026-10-01T00:00:00+08:00'), replace(approval, seed_sha=sha(self.fixture.seed)), replace(approval, expected_generation=0)):
            with self.assertRaises(ValueError): restore_verified_version(c, current, self.fixture.old_ref, bad)
        tx = restore_verified_version(c, current, self.fixture.old_ref, approval)
        c.pages.on_create = lambda _: live.set(self.fixture.old_site)
        c.request_pages_once(tx['key'], tx['fence']); c.observe_pages(tx['key'], tx['fence']); c.verify_live(tx['key'], tx['fence'])
        result = c.finalize_success(tx['key'], tx['fence'], c.store.read().head)
        self.assertEqual(result['kind'], 'manual-restore'); self.assertEqual(result['rollbackOf'], 1)
        self.assertEqual(result['pointer']['generation'], 2); self.assertEqual(live.body, self.fixture.old_site)
        restored = load_verified_baseline(c.store, c.archive, verifier(live), sha(self.fixture.old_site), 2)
        self.assertEqual(restored.closure, self.fixture.old); self.assertEqual(len(c.pages.creates), 2)
        corrupted = dict(self.fixture.old); corrupted['site.zip'] += b'bad'
        with self.assertRaises(ValueError): verify_closure(corrupted)
        from pipeline.acquisition_state import policy_files
        policies = policy_files(); policies['source-publication.json'] += b' '
        with patch('pipeline.acquisition_state.policy_files', return_value=policies), self.assertRaises(ValueError): verify_closure(self.fixture.old)

    @cases('G01', 'G02', 'G03', 'G04')
    def test_source_date_revision_license_rate_limit_and_capacity_guards_preserved(self):
        p = self.fixture.baseline.payload
        self.assertEqual(gate(p, p, '2026-10-13'), 'no-op-identical')
        self.assertEqual(gate(p, p, '2026-10-18'), 'no-op-closed')
        self.assertEqual(target_day(datetime(2026, 10, 14, 1, tzinfo=TPE), '2026-10-13'), '2026-10-13')
        for target in ('2026-10-14', '2027-01-04'):
            with self.assertRaises(ValueError): gate(p, p, target)
        for key, value in [('sha256', '0'*64), ('asOf', '2026-10-12'), ('licenseStatus', 'pending'), ('fetchStatus', 'error')]:
            changed = copy.deepcopy(p); changed['sources']['quotes'][key] = value
            with self.assertRaises(ValueError): gate(changed, p, '2026-10-13')
        for code in (403, 429):
            with patch('pipeline.common.urlopen', side_effect=HTTPError('https://example.invalid', code, 'refused', {}, None)) as api:
                with self.assertRaises(HTTPError): get_json('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes')
                self.assertEqual(api.call_count, 1)
        for total in (None, 5*1024**3):
            with tempfile.TemporaryDirectory() as t:
                backend = FilesystemReleases(t)
                with patch.object(backend, 'total_bytes', return_value=total), patch.object(backend, 'create') as create:
                    with self.assertRaises(ValueError): ReleaseArchive(backend).archive_candidate(self.fixture.new)
                    create.assert_not_called()

    @cases('P10', 'W01', 'W03')
    def test_real_transports_closed_and_legacy_bypass_not_claimed_ready(self):
        api = Mock(side_effect=AssertionError('Real API unexpectedly called'))
        real = ReleaseArchive(GitHubReleases(api))
        with self.assertRaises(PermissionError): real.archive_candidate(self.fixture.new, capability=True)
        with self.assertRaises(PermissionError): GitHubPages(api).create_once({}, lambda _: None, capability=True)
        with self.assertRaises(PermissionError): GitHubState(api).child('a'*40, {}, 'forbidden', capability=True)
        with self.assertRaises(PermissionError): GitHubState(api).advance('a'*40, 'b'*40, capability=True)
        api.assert_not_called(); self.assertEqual(self.network_spy.call_count, 0)
        from scripts.audit_workflows import audit, LEGACY_SHA256
        self.assertEqual(len(audit()), 5)
        self.assertEqual(sha((ROOT/'.github/workflows/pages-release.yml').read_bytes()), LEGACY_SHA256)
        self.assertNotIn('PublicationCoordinator', (ROOT/'.github/workflows/pages-release.yml').read_text())
        # Existing first-release route must be integrated/retired in 4C-2D before arming new real writes.
        from pipeline.daily_policy import load
        self.assertFalse(load()['scheduleEnabled']); self.assertFalse(load()['productionPublicationAuthorized']); self.assertFalse(load()['rollbackAuthorized'])
        commands=json.loads((ROOT/'package.json').read_bytes())['scripts']
        self.assertTrue(all('pipeline.verified_baseline' in commands[k] for k in ('data','data:strict','data:candidate')))
        with tempfile.TemporaryDirectory() as t:
            result=subprocess.run([sys.executable,'-m','pipeline.daily_release','--output',str(Path(t)/'no-fetch'),
                '--target-date','2026-10-14','--run-id','1','--fetch-current'],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertIn('pipeline.verified_baseline',result.stderr)
            self.assertFalse((Path(t)/'no-fetch').exists())

    @cases('B01', 'W03')
    def test_workflow_entry_missing_pointer_makes_zero_financial_calls(self):
        from pipeline.verified_baseline import main
        api = Mock(side_effect=HTTPError('https://api.github.com/state',404,'not initialized',{},None))
        with tempfile.TemporaryDirectory() as t, patch('pipeline.verified_baseline.acquire_candidate') as acquire:
            out = Path(t)/'failure'
            result = main(['--expected-zip-sha256',sha(self.fixture.old_site),'--expected-generation','0',
                '--target-date','2026-10-14','--run-id','1001','--run-attempt','1','--slot','manual-1830',
                '--deadline',EXPIRES,'--output',str(out),'--fetch-current'],api=api)
            self.assertEqual(result,2); acquire.assert_not_called(); self.assertEqual(api.call_count,1)
            failure=json.loads((out/'failure.json').read_bytes()); self.assertFalse(failure['fallbackUsed'])

    @cases('B02', 'B03', 'W03')
    def test_github_read_adapters_exact_ids_blob_hash_and_bounded_http(self):
        c,b,live=self.environment(); calls=[]; backend=c.archive.backend
        def api(method,path,payload=None,**kwargs):
            self.assertEqual(method,'GET'); calls.append(path)
            if path.startswith('/git/ref/tags/'):
                return {'object':{'type':'commit','sha':self.fixture.commit}}
            if path.startswith('/releases/assets/'):
                aid=int(path.rsplit('/',1)[-1])
                return backend.download(self.fixture.old_ref['releaseId'],aid)
            if '/assets?' in path:
                return backend.get(int(path.split('/')[2]))['assets']
            if path.startswith('/releases/'):
                return backend.get(int(path.rsplit('/',1)[-1]))
            raise AssertionError(path)
        loaded,_=ReleaseArchive(GitHubReleases(api)).load(self.fixture.old_ref)
        self.assertEqual(loaded,self.fixture.old); self.assertFalse(any('latest' in p for p in calls))
        import hashlib
        source=c.store.read(); hashes={hashlib.sha1(b'blob '+str(len(v)).encode()+b'\0'+v).hexdigest():v for v in source.files.values()}
        tree=[{'path':n,'mode':'100644','type':'blob','sha':hashlib.sha1(b'blob '+str(len(v)).encode()+b'\0'+v).hexdigest()} for n,v in source.files.items()]
        def git_api(method,path,payload=None,**kwargs):
            self.assertEqual(method,'GET')
            if '/git/ref/' in path:return {'ref':'refs/heads/scanner-release-state','object':{'type':'commit','sha':source.head}}
            if '/git/commits/' in path:return {'tree':{'sha':'a'*40}}
            if '/git/trees/' in path:return {'truncated':False,'tree':tree}
            if '/git/blobs/' in path:return {'encoding':'base64','content':base64.b64encode(hashes[path.rsplit('/',1)[-1]]).decode()}
            raise AssertionError(path)
        self.assertEqual(StateStore(GitHubState(git_api)).read().state,source.state)
        from pipeline.github_transport import GitHubAPI
        class Response:
            status=200
            def __init__(self,body):self.body=body
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):self.limit=limit;return self.body
        opener=Mock(return_value=Response(b'{"ok":true}')); client=GitHubAPI(opener=opener)
        self.assertEqual(client('GET','/releases/1'),{'ok':True})
        with self.assertRaises(PermissionError):client('POST','/releases',{})
        self.assertEqual(opener.call_count,1)
        for code in (403,429):
            opener=Mock(side_effect=HTTPError('https://api.github.com',code,'stop',{},None))
            with self.assertRaises(HTTPError):GitHubAPI(opener=opener)('GET','/releases/1')
            self.assertEqual(opener.call_count,1)
        opener=Mock(side_effect=[HTTPError('https://api.github.com',302,'asset',{'Location':'https://release-assets.githubusercontent.com/fixture'},None),Response(b'asset')])
        self.assertEqual(GitHubAPI('offline-test-token',opener)('GET','/releases/assets/1',binary=True),b'asset')
        self.assertNotIn('Authorization',opener.call_args_list[1].args[0].headers)

    @cases('C02','P03','W03')
    def test_disabled_mutation_wire_contracts_use_only_in_memory_clients(self):
        # Exercise the otherwise closed wire paths only with mocked gates AND no-network clients.
        from pipeline.github_transport import GitHubAPI
        class Response:
            status=201
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"id":17}'
        opener=Mock(return_value=Response()); client=GitHubAPI('synthetic-test-token',opener,capability=object())
        with patch('pipeline.github_transport.require_remote',return_value=None):
            self.assertEqual(client('POST','/releases',{'tag_name':'offline'})['id'],17)
            request=opener.call_args.args[0]
            self.assertEqual(request.get_method(),'POST'); self.assertEqual(json.loads(request.data),{'tag_name':'offline'})
            client('POST','uploads:/releases/17/assets?name=site.zip',b'original bytes')
            request=opener.call_args.args[0]
            self.assertTrue(request.full_url.startswith('https://uploads.github.com/repos/0857ken/tw-market-scanner/'))
            self.assertEqual(request.data,b'original bytes')
            client('PATCH','/git/refs/heads/scanner-release-state',{'sha':'c'*40,'force':False})
            self.assertEqual(opener.call_args.args[0].get_method(),'PATCH')
            self.assertFalse(json.loads(opener.call_args.args[0].data)['force'])
        h='a'*40;c='c'*40;calls=[]
        def api(method,path,payload=None,**kwargs):
            calls.append((method,path,payload))
            if method=='GET' and path=='/git/commits/'+h:return {'tree':{'sha':'d'*40}}
            if method=='GET' and path=='/git/commits/'+c:return {'parents':[{'sha':h}]}
            if path=='/git/blobs':return {'sha':'b'*40}
            if path=='/git/trees':return {'sha':'e'*40}
            if path=='/git/commits':return {'sha':c}
            if path.startswith('/git/refs/'):return {'object':{'sha':c}}
            if path=='/pages/deployments':return {'id':17}
            raise AssertionError((method,path))
        state=GitHubState(api)
        with patch('pipeline.persistent_state.require_remote',return_value=None):
            self.assertEqual(state.child(h,{'state.json':b'{}'},'offline-wire',capability=object()),c)
            state.advance(h,c,capability=object())
        commit=next(payload for method,path,payload in calls if method=='POST' and path=='/git/commits')
        self.assertEqual(commit['parents'],[h]);self.assertEqual(calls[-1][2],{'sha':c,'force':False})
        ids=[]
        class Cap:oidc_token='synthetic-oidc'
        with patch('pipeline.pages_transport.require_remote',return_value=None):
            did=GitHubPages(api).create_once({'phase':'DEPLOY_REQUESTED','deploymentId':None,'pagesArtifactId':99,'key':'f'*64},ids.append,Cap())
        self.assertEqual(did,'17');self.assertEqual(ids,['17'])
        pages=[x for x in calls if x[0]=='POST' and x[1]=='/pages/deployments'];self.assertEqual(len(pages),1)
        self.assertEqual(pages[0][2]['pages_build_version'],'f'*40)
        self.assertEqual(self.network_spy.call_count,0)
