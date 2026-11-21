"""Enforced candidate policy. No setting can enable production or scheduling."""
import hashlib
import math
import re
from .common import ROOT, read_json

PATH = ROOT / 'config/daily-release.json'


def load():
    policy = read_json(PATH)
    required = {'configurationScope': 'candidate-rehearsal-only',
                'profile': 'observation-only', 'frontendId': 'observation-daily-v1',
                'sameDayRevision': 'separate-owner-review', 'calendarVerification': 'partial'}
    for key, value in required.items():
        if policy.get(key) != value:
            raise ValueError('Unsupported candidate policy: ' + key)
    for key in ('scheduleEnabled', 'productionPublicationAuthorized', 'rollbackAuthorized'):
        if policy.get(key) is not False:
            raise ValueError('Candidate code cannot authorize ' + key)
    bounds = {'minimumPriceCoveragePct': (95, 100),
              'maximumCoverageDropPercentagePoints': (0, 2),
              'maximumRosterRelativeChange': (0, .05),
              'maximumRosterAgeCalendarDays': (0, 7)}
    for key, (low, high) in bounds.items():
        value = policy.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Unsafe candidate threshold: ' + key)
    seed = policy.get('approvedFrontendSeedZipSha256')
    if seed is not None and (not isinstance(seed, str) or not re.fullmatch('[a-f0-9]{64}', seed)):
        raise ValueError('Invalid approved frontend seed SHA256')
    return policy


def digest():
    load()
    return hashlib.sha256(PATH.read_bytes()).hexdigest()


def check_seed(expected):
    approved = load()['approvedFrontendSeedZipSha256']
    if approved is not None and approved != expected:
        raise ValueError('Seed differs from configured approved frontend seed')
    # Null permits a manually hash-pinned rehearsal, never a production approval.
    return approved is not None
