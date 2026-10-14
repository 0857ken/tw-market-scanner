import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta

from pipeline.common import ROOT, TPE, read_json
from pipeline.observation_release import check
from pipeline.release_check import check as full_check


class ObservationReleaseTests(unittest.TestCase):
    def setUp(self):
        self.body = (ROOT / 'data/market.json').read_bytes()
        self.approval = read_json(ROOT / 'config/observation-release.json')
        self.now = datetime.fromisoformat(self.approval['approvedAsOf']).replace(hour=18,tzinfo=TPE) + timedelta(days=2)

    def test_dated_observation_does_not_relax_full_strategy(self):
        encoded, report = check(self.body, now=self.now)
        self.assertTrue(report['observationCandidatePassed'])
        self.assertFalse(report['strategyComplete'])
        self.assertFalse(report['latestSessionVerified'])
        self.assertEqual(report['ageCalendarDays'], 2)
        self.assertFalse(report['deploymentAuthorized'])
        with self.assertRaises(ValueError):
            full_check(json.loads(encoded), now=self.now)

    def test_projection_excludes_non_observation_data(self):
        output = json.loads(check(self.body, now=self.now)[0])
        for key in ('indexHistory', 'futures', 'creditHistory'):
            self.assertEqual(output[key], [])
        self.assertTrue(all(s['margin'] is None for s in output['stocks']))
        self.assertTrue(all(not s['institutional'] for s in output['stocks'] if s['market'] == 'TWSE'))

    def test_unapproved_bytes_and_missing_data_rejected(self):
        for body in (b'{}', self.body + b' ', b''):
            with self.assertRaises(ValueError):
                check(body, now=self.now)

    def test_license_not_inferred_from_accessibility(self):
        policy = read_json(ROOT / 'config/source-publication.json')['modules']
        for module in ('quotes', 'tpexQuotes', 'tpexInstitutional'):
            modified = copy.deepcopy(policy)
            modified[module]['status'] = 'pending'
            with self.assertRaises(ValueError):
                check(self.body, policy=modified, now=self.now)

    def mutate(self, callback):
        data = json.loads(self.body)
        callback(data)
        body = json.dumps(data).encode()
        approval = {**self.approval, 'approvedInputSha256': hashlib.sha256(body).hexdigest()}
        return body, approval

    def test_no_demo_or_t86_even_if_digest_is_reviewed(self):
        for mutation in (lambda p: p.update(mode='demo'), lambda p: next(s for s in p['stocks'] if s['market']=='TWSE')['institutional'].append({'date':'2026-10-12','foreignShares':1})):
            body, approval = self.mutate(mutation)
            with self.assertRaises(ValueError):
                check(body, approval=approval, now=self.now)

    def test_failed_source_rejected(self):
        body, approval = self.mutate(lambda p: p['sources']['quotes'].update(status='error'))
        with self.assertRaises(ValueError):
            check(body, approval=approval, now=self.now)

    def test_projection_is_deterministic(self):
        self.assertEqual(check(self.body, now=self.now)[0], check(self.body, now=self.now+timedelta(days=1))[0])

    def test_candidate_cannot_grant_deployment_permission(self):
        with self.assertRaises(ValueError):
            check(self.body, approval={**self.approval, 'deploymentAuthorized':True}, now=self.now)
