"""Offline failure injection against real fixture data; all writes are temporary."""
import copy
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pipeline.common import ROOT, TPE, read_json, write_json
from pipeline.candidate_io import atomic_bytes, exclusive_lock
from pipeline import daily_policy
from pipeline.daily_release import bundle, controlled, encoded, gate, project, sha, verify_bundle
from pipeline.daily_state import commit, restore
from pipeline.package_daily import package
from scripts.audit_workflows import audit, parse


def inventory(directory):
    return {p.relative_to(directory).as_posix(): sha(p.read_bytes())
            for p in directory.rglob('*') if p.is_file()}


class DailyIsolationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_daily import DailyTests
        self.fixture = DailyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.before = inventory(self.fixture.root)

    def test_write_failure_at_each_metadata_file_never_changes_baseline(self):
        for filename in ('source-state.json', 'quality.json', 'market.json', 'daily-attempt.json'):
            with self.subTest(filename=filename):
                def injected(path, value):
                    if Path(path).name == filename:
                        # Simulate a partial write, not only an exception before writing.
                        Path(path).write_text('{"partial":')
                        raise OSError('injected partial ' + filename)
                    return write_json(path, value)
                with patch('pipeline.daily.write_json', side_effect=injected):
                    self.assertEqual(self.fixture.replay(), 2)
                self.assertEqual(inventory(self.fixture.root), self.before)
                self.assertFalse(self.fixture.output.exists())
                attempt = read_json(self.fixture.output.with_name(self.fixture.output.name + '.attempt.json'))
                self.assertIn('injected partial', attempt['error'])

    def test_interrupt_and_directory_publication_failure_can_retry(self):
        with patch('pipeline.daily.write_json', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.fixture.replay()
        self.assertFalse(self.fixture.output.exists())
        self.assertEqual(inventory(self.fixture.root), self.before)
        with patch('pipeline.daily.publish_directory', side_effect=OSError('rename failed')):
            self.assertEqual(self.fixture.replay(), 2)
        self.assertFalse(self.fixture.output.exists())
        self.assertEqual(self.fixture.replay(), 0)
        self.assertEqual(inventory(self.fixture.root), self.before)

    def test_output_cannot_overlap_baseline_or_protected_data(self):
        from pipeline.daily import run_daily
        for output in (self.fixture.root, self.fixture.root/'nested', ROOT/'data/new-candidate', ROOT/'frontend/public/new-candidate'):
            with self.assertRaises((ValueError, FileExistsError)):
                run_daily(self.fixture.root, output_dir=output)
        with self.assertRaises(ValueError):
            run_daily(self.fixture.root)

    def test_raw_snapshot_write_failure_keeps_entire_input_unchanged(self):
        def advance(samples):
            samples['quotes']['date']='2026-10-12'
            for row in samples['quotes']['rows']:
                row['date']='2026-10-12'
        def injected(path, value):
            Path(path).write_text('{"partial":')
            raise OSError('injected raw snapshot failure')
        with patch('pipeline.run.write_json',side_effect=injected):
            self.assertEqual(self.fixture.replay(advance,expected_requests=3),2)
        self.assertFalse(self.fixture.output.exists())
        self.assertEqual(inventory(self.fixture.root),self.before)

    def test_failed_evidence_has_no_success_gate_and_cannot_be_reused(self):
        output=Path(self.fixture.tmp.name)/'evidence'
        def injected(path,value):
            if Path(path).name=='candidate-report.json':
                Path(path).write_text('{"partial":')
                raise OSError('candidate report failure')
            return write_json(path,value)
        p=read_json(ROOT/'data/market.json')
        with patch('pipeline.daily_release.write_json',side_effect=injected):
            with self.assertRaises(OSError):
                controlled(ROOT/'data',output,p['asOf'],datetime(2026,10,14,9,tzinfo=TPE),'failed')
        self.assertEqual(set(inventory(output)),{'failure.json'})
        before=inventory(output)
        with patch('pipeline.daily_release.run_daily') as request:
            with self.assertRaises(FileExistsError):
                controlled(ROOT/'data',output,p['asOf'],datetime(2026,10,14,9,tzinfo=TPE),'retry',True)
            request.assert_not_called()
        self.assertEqual(before,inventory(output))


class CandidatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'policy.json'
        self.policy = read_json(daily_policy.PATH)
        write_json(self.path, self.policy)
        self.patch = patch.object(daily_policy, 'PATH', self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_unsafe_permissions_and_thresholds_fail_closed(self):
        for key, value in [('scheduleEnabled', True), ('productionPublicationAuthorized', True),
                           ('rollbackAuthorized', True), ('minimumPriceCoveragePct', 94),
                           ('maximumCoverageDropPercentagePoints', 3), ('maximumRosterRelativeChange', .06),
                           ('maximumRosterAgeCalendarDays', 8), ('profile', 'strategy'),
                           ('scheduleEnabled', 'false')]:
            with self.subTest(key=key):
                p = {**self.policy, key: value}
                write_json(self.path, p)
                with self.assertRaises(ValueError):
                    daily_policy.load()

    def test_configured_coverage_threshold_changes_real_gate_decision(self):
        p = read_json(ROOT/'data/market.json')
        self.assertEqual(gate(p, p, p['asOf']), 'no-op-identical')
        write_json(self.path, {**self.policy, 'minimumPriceCoveragePct': 100})
        with self.assertRaisesRegex(ValueError, 'coverage abnormal'):
            gate(p, p, p['asOf'])

    def test_seed_pin_is_enforced_and_null_is_only_a_rehearsal(self):
        self.assertFalse(daily_policy.check_seed('a'*64))
        write_json(self.path, {**self.policy, 'approvedFrontendSeedZipSha256': 'a'*64})
        self.assertTrue(daily_policy.check_seed('a'*64))
        with self.assertRaises(ValueError):
            daily_policy.check_seed('b'*64)


class BundleFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = datetime(2026, 10, 14, 9, tzinfo=TPE)
        cls.body, cls.report = project(read_json(ROOT/'data/market.json'), 'fault-fixture', cls.now)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.seed = self.make_seed('seed', b'old frontend')
        self.old = self.root/'old.zip'
        self.receipt = bundle(self.body, self.report, self.seed, self.old)

    def make_seed(self, name, html):
        root = self.root/name
        root.mkdir()
        (root/'index.html').write_bytes(html)
        (root/'.nojekyll').touch()
        write_json(root/'frontend-pin.json', {'frontendId': 'observation-daily-v1',
                   'assets': {p: sha((root/p).read_bytes()) for p in ('index.html', '.nojekyll')}})
        return root

    def next_bundle(self, seed=None):
        path = self.root/'new.zip'
        receipt = bundle(self.body, {**self.report, 'runId': 'second-fixture'}, seed or self.seed, path)
        return path, receipt

    def test_zip_write_or_final_link_failure_never_exposes_partial_zip(self):
        output = self.root/'result.zip'
        for target in ('pipeline.daily_release.zipfile.ZipFile.writestr', 'pipeline.candidate_io.os.link'):
            with patch(target, side_effect=OSError('injected ZIP failure')):
                with self.assertRaises(OSError):
                    bundle(self.body, self.report, self.seed, output)
            self.assertFalse(output.exists())
        receipt = bundle(self.body, self.report, self.seed, output)
        self.assertTrue(verify_bundle(output, receipt, self.seed))
        with self.assertRaises(FileExistsError):
            bundle(self.body, self.report, self.seed, output)

    def test_partial_zip_rejected_without_changing_current(self):
        store = self.root/'state'
        commit(store, self.old, self.receipt, self.seed)
        before = (store/'current.json').read_bytes()
        path, receipt = self.next_bundle()
        path.write_bytes(path.read_bytes()[:100])
        with self.assertRaises(ValueError):
            commit(store, path, receipt, self.seed, self.receipt['zipSha256'])
        self.assertEqual((store/'current.json').read_bytes(), before)
        self.assertEqual((store/(self.receipt['zipSha256']+'.zip')).read_bytes(), self.old.read_bytes())

    def test_interruption_before_and_after_pointer_replace_is_retryable(self):
        from pipeline.candidate_io import atomic_json
        store = self.root/'state'
        commit(store, self.old, self.receipt, self.seed)
        before = (store/'current.json').read_bytes()
        path, receipt = self.next_bundle()
        def fail_before(pointer, value, **kwargs):
            if Path(pointer).name == 'current.json':
                raise OSError('pointer not replaced')
            return atomic_json(pointer, value, **kwargs)
        with patch('pipeline.daily_state.atomic_json', side_effect=fail_before):
            with self.assertRaises(OSError):
                commit(store, path, receipt, self.seed, self.receipt['zipSha256'])
        self.assertEqual((store/'current.json').read_bytes(), before)
        def fail_after(pointer, value, **kwargs):
            atomic_json(pointer, value, **kwargs)
            if Path(pointer).name == 'current.json':
                raise OSError('ambiguous completion after pointer replacement')
        with patch('pipeline.daily_state.atomic_json', side_effect=fail_after):
            with self.assertRaises(OSError):
                commit(store, path, receipt, self.seed, self.receipt['zipSha256'])
        done = (store/'current.json').read_bytes()
        commit(store, path, receipt, self.seed, self.receipt['zipSha256'])
        self.assertEqual((store/'current.json').read_bytes(), done)

    def test_corrupt_preexisting_store_zip_is_not_overwritten(self):
        store = self.root/'state'
        commit(store, self.old, self.receipt, self.seed)
        before = (store/'current.json').read_bytes()
        path, receipt = self.next_bundle()
        corrupt = store/(receipt['zipSha256']+'.zip')
        corrupt.write_bytes(b'old partial artifact')
        with self.assertRaisesRegex(ValueError, 'quarantine'):
            commit(store, path, receipt, self.seed, self.receipt['zipSha256'])
        self.assertEqual(corrupt.read_bytes(), b'old partial artifact')
        self.assertEqual((store/'current.json').read_bytes(), before)

    def test_restore_across_frontend_versions_requires_prior_seed(self):
        store = self.root/'state'
        commit(store, self.old, self.receipt, self.seed)
        next_seed = self.make_seed('next-seed', b'new approved frontend')
        path, receipt = self.next_bundle(next_seed)
        commit(store, path, receipt, next_seed, self.receipt['zipSha256'])
        before = (store/'current.json').read_bytes()
        with self.assertRaises(ValueError):
            restore(store, self.receipt['zipSha256'], next_seed, receipt['zipSha256'])
        self.assertEqual((store/'current.json').read_bytes(), before)
        restored = restore(store, self.receipt['zipSha256'], self.seed, receipt['zipSha256'])
        self.assertEqual(restored['zipSha256'], self.receipt['zipSha256'])
        self.assertEqual((store/(self.receipt['zipSha256']+'.zip')).read_bytes(), self.old.read_bytes())
        self.assertEqual(restore(store, self.receipt['zipSha256'], self.seed, receipt['zipSha256']), restored)

    def test_restore_rejects_stale_cas_corrupt_prior_and_path_traversal(self):
        store = self.root/'state'
        commit(store, self.old, self.receipt, self.seed)
        path, receipt = self.next_bundle()
        commit(store, path, receipt, self.seed, self.receipt['zipSha256'])
        before = (store/'current.json').read_bytes()
        with self.assertRaises(ValueError):
            restore(store, self.receipt['zipSha256'], self.seed, '0'*64)
        (store/(self.receipt['zipSha256']+'.zip')).write_bytes(b'broken prior')
        with self.assertRaises(ValueError):
            restore(store, self.receipt['zipSha256'], self.seed, receipt['zipSha256'])
        with self.assertRaises(ValueError):
            restore(store, '../outside', self.seed, receipt['zipSha256'])
        self.assertEqual((store/'current.json').read_bytes(), before)

    def test_package_failure_is_not_a_reusable_success_output(self):
        candidate = self.root/'candidate'
        candidate.mkdir()
        (candidate/'candidate-market.json').write_bytes(self.body)
        write_json(candidate/'candidate-report.json', self.report)
        write_json(candidate/'gate.json', {'decision': 'candidate', 'runId': self.report['runId'],
                   'target': self.report['asOf'], 'candidatePolicySha256': daily_policy.digest()})
        from pipeline.package_daily import write_json as real_write
        def fail_receipt(path, value):
            if Path(path).name == 'receipt.json':
                raise OSError('receipt write failed')
            return real_write(path, value)
        output = self.root/'package'
        with patch('pipeline.package_daily.write_json', side_effect=fail_receipt):
            with self.assertRaises(OSError):
                package(candidate, self.old, self.receipt['zipSha256'], output)
        self.assertFalse(output.exists())
        package(candidate, self.old, self.receipt['zipSha256'], output)
        original = inventory(output)
        with self.assertRaises(FileExistsError):
            package(candidate, self.old, self.receipt['zipSha256'], output)
        self.assertEqual(inventory(output), original)

    def test_unapproved_stock_scope_or_policy_cannot_create_final_zip(self):
        p=json.loads(self.body)
        p['stocks'][0]['margin']={'date':p['asOf'],'balanceShares':1,'limitShares':100,'usagePct':1}
        changed=encoded(p)
        with self.assertRaises(ValueError):
            bundle(changed,{**self.report,'publishedDataSha256':sha(changed)},self.seed,self.root/'bad.zip')
        self.assertFalse((self.root/'bad.zip').exists())
        with self.assertRaises(ValueError):
            bundle(self.body,{**self.report,'candidatePolicySha256':'0'*64},self.seed,self.root/'bad-policy.zip')
        self.assertFalse((self.root/'bad-policy.zip').exists())


class ProcessInterruptionTests(unittest.TestCase):
    def test_live_lock_blocks_and_killed_owner_leaves_only_harmless_file(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)/'.lock'
            code = "from pipeline.candidate_io import exclusive_lock; import sys;\nwith exclusive_lock(sys.argv[1]):\n print('locked',flush=True)\n sys.stdin.read()"
            child = subprocess.Popen([sys.executable, '-B', '-c', code, str(path)], cwd=ROOT,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'locked')
                with self.assertRaises(BlockingIOError):
                    with exclusive_lock(path):
                        pass
                child.kill()
                child.wait(timeout=5)
                self.assertTrue(path.exists())
                with exclusive_lock(path):
                    pass
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                child.stdin.close()
                child.stdout.close()

    def test_process_exit_after_temp_write_never_publishes_partial_file(self):
        with tempfile.TemporaryDirectory() as t:
            output = Path(t)/'complete.zip'
            code = "from pipeline.candidate_io import atomic_bytes; import os,sys; os.link=lambda *a:os._exit(23); atomic_bytes(sys.argv[1],b'complete candidate',immutable=True)"
            r = subprocess.run([sys.executable, '-B', '-c', code, str(output)], cwd=ROOT, timeout=10)
            self.assertEqual(r.returncode, 23)
            self.assertFalse(output.exists())
            self.assertTrue(list(Path(t).glob('*.pending')))
            atomic_bytes(output, b'complete candidate', immutable=True)
            self.assertEqual(output.read_bytes(), b'complete candidate')


class WorkflowSafetyTests(unittest.TestCase):
    def test_all_workflows_including_pages_are_audited(self):
        self.assertEqual(set(audit()), {'ci.yml', 'deploy.yml', 'pages-release.yml', 'update-data.yml', 'package-daily.yml'})

    def test_schedule_permissions_unknown_file_and_legacy_mutations_fail(self):
        for filename, mutate in [
            ('ci.yml', lambda s: s.replace('  workflow_dispatch:', "  schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:")),
            ('update-data.yml', lambda s: s.replace('contents: read', 'contents: write')),
            ('package-daily.yml', lambda s: s.replace('contents: read', 'contents: read\n  pages: write')),
            ('ci.yml', lambda s: s.replace('    runs-on:', '    permissions: write-all\n    runs-on:', 1)),
            ('deploy.yml', lambda s: s.replace('    runs-on:', '    environment: github-pages\n    runs-on:', 1)),
            ('pages-release.yml', lambda s: s.replace('PUBLISH-4b1-rc1', 'OTHER')),
        ]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as t:
                directory = Path(t)/'workflows'
                shutil.copytree(ROOT/'.github/workflows', directory)
                path = directory/filename
                path.write_text(mutate(path.read_text()))
                with self.assertRaises(ValueError):
                    audit(directory)
        with tempfile.TemporaryDirectory() as t:
            directory = Path(t)/'workflows'
            shutil.copytree(ROOT/'.github/workflows', directory)
            (directory/'surprise.yaml').write_text('on: workflow_dispatch\n')
            with self.assertRaises(ValueError):
                audit(directory)

    def test_yaml_duplicates_aliases_and_inline_schedule_fail(self):
        with self.assertRaises(ValueError):
            parse('on: workflow_dispatch\non: schedule\n')
        with self.assertRaises(ValueError):
            parse('a: &x {contents: read}\nb: *x\n')
        with tempfile.TemporaryDirectory() as t:
            directory = Path(t)/'workflows'
            shutil.copytree(ROOT/'.github/workflows', directory)
            (directory/'update-data.yml').write_text('on: {schedule: [{cron: "0 0 * * *"}]}\n')
            with self.assertRaises(ValueError):
                audit(directory)

    def test_old_clis_exit_without_requests_or_data_changes(self):
        before = inventory(ROOT/'data')
        for module in ('pipeline.run', 'pipeline.daily'):
            r = subprocess.run([sys.executable, '-B', '-m', module, '--strict'], cwd=ROOT,
                               capture_output=True, text=True, timeout=10)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('pipeline.daily_release', r.stderr)
        self.assertEqual(before, inventory(ROOT/'data'))
