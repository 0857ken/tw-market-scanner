"""Check current freshness and source rights before a manual Pages release."""
from datetime import datetime

from .common import ROOT, TPE, expected_session, read_json
from .schema import validate


def check(payload, now=None, policy=None):
    validate(payload)
    now = now or datetime.now(TPE)
    policy = policy or read_json(ROOT / 'config/source-publication.json')['modules']
    if payload['mode'] != 'live':
        raise ValueError('A real EOD snapshot is required')
    if payload.get('researchVersion') and any(m.get('calendarStatus') != 'verified' for m in payload['research']['markets'].values()):
        raise ValueError('Independent market calendars not verified')
    expected, known = expected_session(now, payload.get('calendar', {}).get('rows', []))
    if not known:
        raise ValueError('Current trading calendar not verified')
    required=('quotes','companies','tpexQuotes','tpexCompanies') if payload.get('researchVersion') else ('quotes','companies')
    for module in required:
        source = payload['sources'].get(module, {})
        if source.get('status') != 'fresh' or not source.get('asOf') or source['asOf'] < expected:
            raise ValueError(f'{module}: stale or failed for current expected session {expected}')
    populated = {'quotes', 'companies', 'calendar'}
    if payload.get('researchVersion'):
        populated.update(('tpexQuotes','tpexCompanies'))
        if any(s.get('events') for s in payload['stocks'] if s.get('market')=='TPEx'):populated.add('tpexEvents')
    if payload['indexHistory']:
        populated.update(('index', 'indexHistory'))
    if payload['futures']:
        populated.add('futures')
    if any(stock.get('margin') for stock in payload['stocks']):
        populated.add('margin')
    if any(stock.get('institutional') for stock in payload['stocks'] if stock.get('market')!='TPEx'):
        populated.add('institutional')
    if any(stock.get('institutional') for stock in payload['stocks'] if stock.get('market')=='TPEx'):
        populated.add('tpexInstitutional')
    if payload['creditHistory']:
        populated.add('credit')
    for module in populated:
        if policy.get(module, {}).get('status') != 'verified-open-data':
            raise ValueError(f'{module}: redistribution rights pending')
    return expected


if __name__ == '__main__':
    print('Release data checked against current session:', check(read_json(ROOT / 'data/market.json')))
