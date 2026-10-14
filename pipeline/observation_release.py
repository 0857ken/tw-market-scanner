"""Independent, fail-closed observation candidate gate. No fetch or deployment.

The full strategy release_check remains independent and unmodified.
Approval pins input bytes; projection publishes only the observation surface.
"""
import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path

from .common import ROOT, TPE, read_json
from .schema import validate

MODULES = ('quotes', 'companies', 'tpexQuotes', 'tpexCompanies',
           'calendar', 'tpexEvents', 'tpexInstitutional')


def check(body, approval=None, policy=None, now=None):
    approval = approval or read_json(ROOT / 'config/observation-release.json')
    policy = policy or read_json(ROOT / 'config/source-publication.json')['modules']
    now = now or datetime.now(TPE)
    if approval.get('profile') != 'observation-only' or approval.get('deploymentAuthorized') is not False:
        raise ValueError('Candidate approval must not authorize deployment')
    if hashlib.sha256(body).hexdigest() != approval['approvedInputSha256']:
        raise ValueError('Unapproved input bytes: SHA256 mismatch')
    payload = json.loads(body)
    validate(payload, now=now)
    if payload['mode'] != 'live' or payload['asOf'] != approval['approvedAsOf']:
        raise ValueError('Approved real snapshot/date required')
    if payload['creditHistory'] or payload['creditRule']['status'] != 'pending':
        raise ValueError('Credit strategy must remain frozen')
    for module in MODULES:
        if policy.get(module, {}).get('status') != 'verified-open-data':
            raise ValueError(f'{module}: redistribution evidence missing')
    for module in ('quotes', 'companies', 'tpexQuotes', 'tpexCompanies', 'tpexInstitutional'):
        source = payload['sources'].get(module, {})
        if source.get('status') in ('error', 'unavailable', 'imported') or not source.get('sha256') or not source.get('asOf'):
            raise ValueError(f'{module}: no valid approved source snapshot')
    for stock in payload['stocks']:
        if stock.get('market') not in ('TWSE', 'TPEx'):
            raise ValueError('Ordinary stock market required')
        if stock['market'] == 'TWSE' and stock.get('institutional'):
            raise ValueError('TWSE T86 prohibited')
        if any(row.get('adjustedClose') is not None for row in stock['history']):
            raise ValueError('Adjusted prices not approved in this candidate')
    output = copy.deepcopy(payload)
    output['indexHistory'] = output['futures'] = output['creditHistory'] = []
    for key in ('overnight', 'branches'):
        output.pop(key, None)
    for stock in output['stocks']:
        stock['margin'] = None
        stock.pop('intraday', None)
    output['sources'] = {k: v for k, v in output['sources'].items()
                         if k in MODULES or k in ('credit', 'institutional')}
    output['observationProfile'] = {k: approval[k] for k in ('profile', 'version', 'enabled', 'disabled', 'priceBasis', 'calendarVerification')}
    validate(output, now=now)
    encoded = (json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    report = {
        'profile': 'observation-only', 'observationCandidatePassed': True,
        'strategyComplete': False, 'deploymentAuthorized': False,
        'inputSha256': approval['approvedInputSha256'],
        'publishedDataSha256': hashlib.sha256(encoded).hexdigest(),
        'version': approval['version'], 'asOf': output['asOf'],
        'generatedAt': output['generatedAt'],
        'ageCalendarDays': (now.astimezone(TPE).date() - datetime.fromisoformat(output['asOf']).date()).days,
        'latestSessionVerified': False, 'calendarVerification': 'partial',
        'marketDates': {m: output['sources'][k]['asOf'] for m, k in [('TWSE','quotes'),('TPEx','tpexQuotes')]},
        'sourceVersions': {k: {'asOf': output['sources'][k].get('asOf'), 'sha256': output['sources'][k].get('sha256'), 'url': output['sources'][k].get('url'), 'fetchedAt': output['sources'][k].get('fetchedAt')} for k in MODULES},
        'enabled': approval['enabled'], 'disabled': approval['disabled'],
        'freshnessPolicy': approval['freshnessPolicy']
    }
    return encoded, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    body, report = check((ROOT / 'data/market.json').read_bytes())
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'market.json').write_bytes(body)
        (args.output / 'observation-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
