"""Strict adapters: official field names, dates and units, with no missing-to-zero coercion."""
import re
from .common import iso_date, number


def companies(raw):
    out = []
    for r in raw:
        symbol = str(r.get('公司代號', '')).strip()
        if not re.fullmatch(r'\d{4}', symbol):
            continue
        out.append({'symbol': symbol, 'name': r['公司簡稱'].strip(),
                    'sector': '產業 ' + r['產業別'].strip(), 'sectorCode': r['產業別'].strip(),
                    'issuedShares': number(r.get('已發行普通股數或TDR原股發行股數')),
                    'date': iso_date(r['出表日期'])})
    if not out or len({r['date'] for r in out}) != 1 or len({r['symbol'] for r in out}) != len(out):
        raise ValueError('Company roster empty, duplicate, or mixed-date')
    return out[0]['date'], out


def quotes(raw):
    out = []
    for r in raw:
        if not re.fullmatch(r'\d{4}', str(r.get('Code', ''))):
            continue
        close, volume = number(r.get('ClosingPrice')), number(r.get('TradeVolume'))
        if close is not None and close <= 0 or volume is not None and volume < 0:
            raise ValueError('Invalid price or volume')
        out.append({'symbol': r['Code'], 'name': r['Name'].strip(), 'date': iso_date(r['Date']),
                    'close': close, 'volumeShares': volume, 'changeAmount': number(r.get('Change')),
                    'status': 'ok' if close is not None else 'no_trade'})
    if not out or len({r['date'] for r in out}) != 1 or len({r['symbol'] for r in out}) != len(out):
        raise ValueError('Quote snapshot empty, duplicate, or mixed-date')
    return out[0]['date'], out


def index(raw):
    out = []
    for r in raw:
        if r.get('指數') != '發行量加權股價指數':
            continue
        close = number(r.get('收盤指數'))
        if close is None or close <= 0:
            raise ValueError('Missing TAIEX')
        out.append({'date': iso_date(r['日期']), 'close': close,
                    'changePct': number(r.get('漲跌百分比'))})
    if len(out) != 1:
        raise ValueError('Expected exactly one TAIEX row')
    return out[0]['date'], out


def index_history(raw):
    out = [{'date': iso_date(r['Date']), 'close': number(r['TAIEX']),
            'volumeShares': number(r.get('TradeVolume'))} for r in raw]
    if not out or any(r['close'] is None or r['close'] <= 0 for r in out):
        raise ValueError('Invalid FMTQIK')
    out.sort(key=lambda r: r['date'])
    if len({r['date'] for r in out}) != len(out):
        raise ValueError('Duplicate FMTQIK date')
    return out[-1]['date'], out


def rwd_date(raw, expected):
    if not isinstance(raw, dict) or raw.get('stat') != 'OK':
        raise ValueError('Official endpoint has no confirmed OK data; not proof of a holiday')
    actual = iso_date(raw['date'])
    if actual != expected:
        raise ValueError(f'Requested {expected}, returned {actual}')
    return actual


def t86(raw, expected):
    d = rwd_date(raw, expected)
    fields = raw['fields']
    required = {'foreignShares': '外陸資買賣超股數(不含外資自營商)',
                'trustShares': '投信買賣超股數', 'dealerShares': '自營商買賣超股數',
                'dealerOwnShares': '自營商買賣超股數(自行買賣)',
                'dealerHedgeShares': '自營商買賣超股數(避險)',
                'totalShares': '三大法人買賣超股數'}
    offsets = {key: fields.index(name) for key, name in required.items()}
    i_code = fields.index('證券代號')
    out = []
    for row in raw['data']:
        symbol = str(row[i_code]).strip()
        if not re.fullmatch(r'\d{4}', symbol):
            continue
        values = {k: number(row[i]) for k, i in offsets.items()}
        # If any component is missing, preserve it as null and mark incomplete.
        complete = all(v is not None for v in values.values())
        if complete and (values['dealerShares'] != values['dealerOwnShares'] + values['dealerHedgeShares'] or
                         values['totalShares'] != values['foreignShares'] + values['trustShares'] + values['dealerShares']):
            raise ValueError(f'T86 total mismatch: {symbol}')
        out.append({'symbol': symbol, 'date': d, **values, 'status': 'ok' if complete else 'incomplete'})
    if not out or len({r['symbol'] for r in out}) != len(out):
        raise ValueError('Empty/duplicate T86')
    return d, out


def margin(raw, expected):
    d = rwd_date(raw, expected)
    tables = raw.get('tables', [raw])
    table = next((t for t in tables if '代號' in t.get('fields', [])), None)
    if table is None:
        raise ValueError('Missing individual margin table')
    fields = table['fields']
    # First repeated group is financing, second is securities lending.
    ib, il = fields.index('今日餘額'), fields.index('次一營業日限額')
    ic = fields.index('代號')
    out = []
    for r in table['data']:
        symbol = r[ic].strip()
        if not re.fullmatch(r'\d{4}', symbol):
            continue
        bal, lim = number(r[ib]), number(r[il])
        if bal is not None and bal < 0 or lim is not None and lim < 0:
            raise ValueError('Negative margin balance or limit')
        out.append({'symbol': symbol, 'date': d,
                    'balanceShares': bal * 1000 if bal is not None else None,
                    'limitShares': lim * 1000 if lim is not None else None,
                    'usagePct': bal / lim * 100 if bal is not None and lim is not None and lim > 0 else None,
                    'usagePctBasis': 'today-balance/next-session-limit', 'sourceUnit': 'lots', 'lotSize': 1000})
    if not out or len({r['symbol'] for r in out}) != len(out):
        raise ValueError('Empty/duplicate margin')
    return d, out


def futures(raw):
    identities = {'外資及陸資': 'foreign', '投信': 'trust', '自營商': 'dealer'}
    out, dates = {}, set()
    for r in raw:
        if r.get('ContractCode') != '臺股期貨' or r.get('Item') not in identities:
            continue
        key = identities[r['Item']]
        if key in out:
            raise ValueError('Duplicate TX identity; do not sum across products/dates')
        dates.add(iso_date(r['Date']))
        net, long, short = [number(r.get(k)) for k in ('OpenInterest(Net)', 'OpenInterest(Long)', 'OpenInterest(Short)')]
        if net is None or long is None or short is None or net != long - short:
            raise ValueError('Missing/mismatched TX open interest')
        if not all(v.is_integer() for v in (net, long, short)):
            raise ValueError('Fractional contracts')
        out[key] = int(net)
    if set(out) != set(identities.values()) or len(dates) != 1:
        raise ValueError('TX requires all three identities and one date')
    d = dates.pop()
    return d, [{'date': d, **out, 'contract': 'TX', 'unit': 'contracts',
                'scope': '官方依日期 TX 法人淨未平倉，各到期月份合計；非盤中或夜盤報價'}]
