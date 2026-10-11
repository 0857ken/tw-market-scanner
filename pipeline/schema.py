"""Strict canonical v2 contract, also validated independently by the frontend."""
import math
import re
from datetime import date, datetime
from urllib.parse import urlparse


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('ISO date required')
    return date.fromisoformat(value)


def valid_number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def ordered(rows, numeric_fields=(), positive_fields=()):
    previous = ''
    for row in rows:
        valid_date(row['date'])
        if row['date'] <= previous:
            raise ValueError('Dates must be ascending and unique')
        previous = row['date']
        for key in numeric_fields:
            value = row.get(key)
            if value is not None and not valid_number(value):
                raise ValueError(f'Invalid {key}')
        for key in positive_fields:
            value = row.get(key)
            if value is not None and value <= 0:
                raise ValueError(f'Nonpositive {key}')


def validate(payload):
    if payload.get('schemaVersion') != 2 or payload.get('mode') not in ('live', 'unavailable'):
        raise ValueError('Canonical schemaVersion 2 live/unavailable required')
    generated = datetime.fromisoformat(payload['generatedAt'])
    if generated.tzinfo is None:
        raise ValueError('generatedAt needs a timezone')
    as_of = payload.get('asOf')
    if as_of:
        valid_date(as_of)
        if as_of > payload['generatedAt'][:10]:
            raise ValueError('Future asOf')
    elif payload['mode'] == 'live':
        raise ValueError('live needs observed asOf')
    if not isinstance(payload.get('sources'), dict):
        raise ValueError('Module provenance required')
    seen = set()
    for stock in payload['stocks']:
        symbol = stock['symbol']
        if not isinstance(symbol, str) or not re.fullmatch('[0-9]{4}', symbol) or symbol in seen or not isinstance(stock.get('name'), str):
            raise ValueError('Invalid/duplicate symbol')
        seen.add(symbol)
        ordered(stock['history'], ('close', 'volumeShares', 'changeAmount'), ('close',))
        if any(r.get('volumeShares') is not None and r['volumeShares'] < 0 for r in stock['history']):
            raise ValueError('Negative volume')
        if stock['history'] and stock['history'][-1]['date'] > as_of:
            raise ValueError('Stock observation newer than quote asOf')
        ordered(stock.get('institutional', []), ('foreignShares', 'trustShares', 'dealerShares', 'totalShares'))
        if stock.get('margin'):
            valid_date(stock['margin']['date'])
            for key in ('balanceShares', 'limitShares', 'usagePct'):
                value = stock['margin'].get(key)
                if value is not None and (not valid_number(value) or value < 0):
                    raise ValueError('Invalid margin value')
    ordered(payload['indexHistory'], ('close',), ('close',))
    ordered(payload['futures'], ('foreign', 'trust', 'dealer'))
    ordered(payload['creditHistory'], ('hyg', 'shy', 'spy'), ('hyg', 'shy', 'spy'))
    for row in payload['futures']:
        if row.get('contract') != 'TX' or row.get('unit') != 'contracts' or any(not valid_number(row.get(k)) or int(row[k]) != row[k] for k in ('foreign', 'trust', 'dealer')):
            raise ValueError('Futures must be TX net OI in integer contracts')
    if payload['creditHistory'] and (payload['sources'].get('credit', {}).get('priceBasis') != 'adjusted-total-return' or
                                    any(not valid_number(row.get(k)) or row[k] <= 0 for row in payload['creditHistory'] for k in ('hyg', 'shy'))):
        raise ValueError('Credit requires paired adjusted total-return prices')
    for key, source in payload['sources'].items():
        if source.get('status') not in ('fresh', 'stale', 'error', 'unknown', 'unavailable', 'imported'):
            raise ValueError('Invalid source status')
        if source.get('asOf'):
            valid_date(source['asOf'])
            if key != 'calendar' and source['asOf'] > payload['generatedAt'][:10]:
                raise ValueError('Future source observation')
        if source.get('fetchedAt'):
            dt = datetime.fromisoformat(source['fetchedAt'])
            if dt.tzinfo is None:
                raise ValueError('Source timestamp timezone missing')
        for field in ('url', 'license'):
            if source.get(field):
                url = urlparse(source[field])
                if url.scheme != 'https' or not url.hostname or url.username or url.password:
                    raise ValueError('Credential-free source HTTPS URLs required')
    if payload['mode'] == 'live' and (not payload['stocks'] or payload['sources'].get('quotes', {}).get('asOf') != as_of or not re.fullmatch('[a-f0-9]{64}', payload['sources'].get('quotes', {}).get('sha256') or '')):
        raise ValueError('live requires stock observations and source digest')
    return payload
