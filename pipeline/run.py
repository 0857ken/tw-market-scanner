"""Fetch official EOD observations; retain dated history and visible failure states.

Usage: python -m pipeline.run [--strict] [--credit-file rights-cleared.json]
No tokens, no paid APIs, no brokerage SDK, no automatic deployment.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import parsers
from .common import ROOT, TPE, LICENSE, get_json, calendar_rows, expected_session, read_json, write_json, timestamp
from .schema import validate, valid_number

SOURCES = {
    'tpexCompanies': ('TPEx 上櫃公司基本資料', 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O'),
    'tpexQuotes': ('TPEx 上櫃股票收盤行情', 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes'),
    'tpexInstitutional': ('TPEx 上櫃三大法人買賣明細', 'https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading'),
    'companies': ('TWSE 上市公司基本資料', 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'),
    'quotes': ('TWSE 上市個股日成交資訊', 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'),
    'index': ('TWSE 發行量加權股價指數', 'https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX'),
    'indexHistory': ('TWSE 集中市場每日市場成交資訊', 'https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK'),
    'institutional': ('TWSE T86 個股三大法人買賣超', 'https://www.twse.com.tw/rwd/zh/fund/T86'),
    'margin': ('TWSE 融資融券餘額', 'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN'),
    'futures': ('TAIFEX 三大法人依期貨契約及日期', 'https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate'),
    'calendar': ('TWSE 開休市日曆', 'https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule'),
}
PUBLICATION = read_json(ROOT / 'config/source-publication.json')['modules']


def snapshots(data_dir, module):
    rows = [read_json(p) for p in sorted((data_dir / 'raw').glob(f'{module}_*.json'))]
    return rows[-300:]


def collect(data_dir, sources, module, parser, now, params=None, fetcher=None):
    name, url = SOURCES[module]
    prior = sources.get(module, {})
    policy = PUBLICATION[module]
    meta = {'name': name, 'url': url, 'licenseStatus': policy['status'], 'licenseEvidence': policy['evidence'],
            'lastAttemptAt': now.isoformat(timespec='seconds')}
    if policy['status'] != 'verified-open-data':
        sources[module] = {**meta, 'asOf': None, 'status': 'unavailable', 'fetchStatus': 'disabled',
                           'reason': policy['note'], 'rowCount': 0}
        print(f'{module}: DISABLED — publication rights not verified', flush=True)
        return None
    meta['license'] = LICENSE
    try:
        raw, digest, actual_url = (fetcher or get_json)(url, params)
        d, rows = parser(raw)
        if module != 'calendar' and date.fromisoformat(d) > now.astimezone(TPE).date():
            raise ValueError('Source date is in the future')
        history = snapshots(data_dir, module)
        last = history[-1] if history else None
        if last and d < last['date']:
            raise ValueError('Source date regressed; keep last valid snapshot')
        if module in ('quotes', 'tpexQuotes', 'tpexInstitutional'):
            local = now.astimezone(TPE)
            if date.fromisoformat(d).weekday() >= 5 or d == local.date().isoformat() and (local.hour, local.minute) < (16, 30):
                raise ValueError('Not a completed weekday EOD observation')
            calendars = snapshots(data_dir, 'calendar') if module == 'quotes' else []
            if calendars and any(r['date'] == d and r['closed'] for r in calendars[-1]['rows']):
                raise ValueError('Quote date is a known closed session')
        existing = read_json(data_dir / 'raw' / f'{module}_{d}.json')
        if existing:
            canonical = lambda values: sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in values)
            if canonical(existing['rows']) != canonical(rows):
                raise ValueError('Same-date source revision requires explicit review; original retained')
            sources[module] = {**meta, 'url': existing['url'], 'asOf': d, 'fetchedAt': existing['fetchedAt'],
                               'sha256': existing['sha256'], 'rowCount': len(rows), 'fetchStatus': 'ok', 'status': 'unknown',
                               'snapshotAction': 'unchanged', 'lastResponseSha256': digest}
            print(f'{module}: {d}, unchanged snapshot', flush=True)
            return existing
        snap = {'module': module, 'date': d, 'rows': rows, 'url': actual_url,
                'sha256': digest, 'fetchedAt': meta['lastAttemptAt'], 'license': LICENSE}
        write_json(data_dir / 'raw' / f'{module}_{d}.json', snap)
        sources[module] = {**meta, 'url': actual_url, 'asOf': d, 'fetchedAt': snap['fetchedAt'], 'sha256': digest,
                           'rowCount': len(rows), 'fetchStatus': 'ok', 'status': 'unknown'}
        print(f'{module}: {d}, {len(rows)} verified rows', flush=True)
        return snap
    except Exception as exc:
        history = snapshots(data_dir, module)
        last = history[-1] if history else None
        sources[module] = {**prior, **meta, 'fetchStatus': 'error', 'status': 'error',
                           'asOf': last['date'] if last else None,
                           'fetchedAt': last['fetchedAt'] if last else None,
                           'sha256': last['sha256'] if last else None,
                           'rowCount': len(last['rows']) if last else 0,
                           'error': str(exc)}
        print(f'{module}: ERROR {exc}', flush=True)
        return last


def import_credit(path, sources, now):
    if not path:
        sources['credit'] = {'name': 'HYG / SHY / SPY 還原權息價', 'asOf': None,
                             'status': 'unavailable', 'fetchStatus': 'disabled',
                             'reason': '尚無可核實公開轉載權限；Yahoo 個人用途 API 不作預設公開站資料源。'}
        return []
    raw = read_json(path)
    if raw.get('priceBasis') != 'adjusted-total-return' or raw.get('license', {}).get('permitsRedistribution') is not True:
        raise ValueError('Credit import requires adjusted total-return prices and declared redistribution rights')
    if not raw.get('source') or not raw.get('license', {}).get('url'):
        raise ValueError('Credit source and license URL required')
    rows = raw['rows']
    previous = ''
    us_now = now.astimezone(ZoneInfo('America/New_York'))
    for r in rows:
        d = date.fromisoformat(r['date'])
        if r['date'] <= previous or d > us_now.date() or d == us_now.date() and us_now.hour < 16:
            raise ValueError('Credit rows must be ordered, unique and from completed US sessions')
        previous = r['date']
        if any(not valid_number(r.get(k)) or r[k] <= 0 for k in ('hyg', 'shy')):
            raise ValueError('Credit paired adjusted prices missing')
    if not rows:
        raise ValueError('Empty credit file')
    sources['credit'] = {'name': raw['source'], 'asOf': rows[-1]['date'], 'status': 'imported',
                         'fetchStatus': 'imported', 'fetchedAt': timestamp(), 'rowCount': len(rows),
                         'license': raw['license']['url'], 'priceBasis': raw['priceBasis'],
                         'reason': '人工提供且宣告使用權限；需獨立確認公開轉載授權。'}
    return rows


def sessions_between(start, end, calendar):
    closed = {r['date'] for r in calendar if r['closed']}
    out, d, last = [], date.fromisoformat(start), date.fromisoformat(end)
    while d <= last:
        if d.weekday() < 5 and d.isoformat() not in closed:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def build(data_dir, sources, calendar, credit, now):
    if PUBLICATION['institutional']['status'] != 'verified-open-data':
        policy = PUBLICATION['institutional']
        sources['institutional'] = {'name': SOURCES['institutional'][0], 'url': SOURCES['institutional'][1],
                                    'asOf': None, 'status': 'unavailable', 'fetchStatus': 'disabled', 'rowCount': 0,
                                    'licenseStatus': policy['status'], 'licenseEvidence': policy['evidence'], 'reason': policy['note']}
    qsnaps = snapshots(data_dir, 'quotes')
    roster = snapshots(data_dir, 'companies')
    observed_dates = [s['date'] for s in qsnaps]
    as_of = observed_dates[-1] if observed_dates else None
    qdates = sessions_between(observed_dates[0], as_of, calendar) if observed_dates else []
    profiles = {r['symbol']: r for r in (roster[-1]['rows'] if roster else [])}
    prices = {}
    for snap in qsnaps:
        for r in snap['rows']:
            prices.setdefault(r['symbol'], {})[r['date']] = r
    inst = snapshots(data_dir, 'institutional') if PUBLICATION['institutional']['status'] == 'verified-open-data' else []
    imap = {s['date']: {r['symbol']: r for r in s['rows']} for s in inst}
    idates = sessions_between(inst[0]['date'], inst[-1]['date'], calendar) if inst else []
    margins = snapshots(data_dir, 'margin')
    mmap = {r['symbol']: r for r in margins[-1]['rows']} if margins else {}
    stocks = []
    for symbol, profile in sorted(profiles.items()):
        if symbol not in prices:
            continue
        first = min(prices[symbol])
        h = []
        for d in qdates:
            if d < first:
                continue
            r = prices[symbol].get(d)
            h.append({k: r.get(k) for k in ('date', 'close', 'volumeShares', 'changeAmount', 'status')} if r else
                     {'date': d, 'close': None, 'volumeShares': None, 'changeAmount': None, 'status': 'missing'})
        latest = prices[symbol].get(as_of)
        institution = []
        for d in idates:
            r = imap.get(d, {}).get(symbol)
            institution.append({'date': d, **({k: r.get(k) for k in ('foreignShares', 'trustShares', 'dealerShares', 'totalShares')}
                                 if r else {k: None for k in ('foreignShares', 'trustShares', 'dealerShares', 'totalShares')})})
        cap = latest['close'] * profile['issuedShares'] / 1e6 if latest and latest['close'] and profile['issuedShares'] else None
        stocks.append({'symbol': symbol, 'name': profile['name'], 'sector': profile['sector'],
                       'sectorCode': profile['sectorCode'], 'market': 'TWSE', 'priceBasis': 'unadjusted',
                       'marketCapM': cap, 'marketCapAsOf': as_of if cap else None, 'profileAsOf': profile['date'],
                       'history': h, 'institutional': institution, 'margin': mmap.get(symbol)})
    ih = {}
    for module in ('indexHistory', 'index'):
        for snap in snapshots(data_dir, module):
            for r in snap['rows']:
                if as_of is None or r['date'] <= as_of:
                    ih[r['date']] = r
    fut = [r for s in snapshots(data_dir, 'futures') for r in s['rows']]
    expected, known = expected_session(now, calendar)
    for key, source in sources.items():
        if key in ('calendar', 'credit') or source.get('fetchStatus') in ('error', 'disabled'):
            continue
        source['status'] = 'fresh' if source.get('asOf') and source['asOf'] >= expected else 'stale'
        if not known or key.startswith('tpex'):
            source['status'] = 'unknown'
    calendar_by_date = {r['date']: r for r in calendar}
    local_day = now.astimezone(TPE).date()
    closed = local_day.weekday() >= 5 or calendar_by_date.get(local_day.isoformat(), {}).get('closed', False)
    calendar_year_known = local_day.year in {int(r['date'][:4]) for r in calendar}
    mode = 'live' if stocks and as_of else 'unavailable'
    return {'schemaVersion': 2, 'mode': mode, 'asOf': as_of, 'generatedAt': now.astimezone(TPE).isoformat(timespec='seconds'),
            'source': 'TWSE / TAIFEX 官方公開資料（盤後）',
            'universe': f'TWSE 上市公司普通股觀察池 {len(stocks)} 檔；排除 ETF、權證、上櫃，非上市櫃全市場',
            'universeMeta': {'market': 'TWSE', 'rosterCount': len(profiles), 'loadedCount': len(stocks),
                             'pointInTimeHistory': False, 'priceBasis': 'unadjusted'},
            'calendar': {'state': ('closed' if closed else 'open') if calendar_year_known else 'unknown',
                         'date': local_day.isoformat(), 'expectedAsOf': expected if known else None,
                         'verified': known, 'rows': calendar},
            'sources': sources, 'stocks': stocks, 'indexHistory': [ih[d] for d in sorted(ih)][-300:],
            'quoteSessions': qdates, 'quoteSnapshotCount': len(observed_dates), 'institutionalSessions': idates, 'futures': fut,
            'creditHistory': credit, 'creditRule': read_json(ROOT / 'config/credit-rule.json'),
            'features': {'intraday': 'unavailable', 'branches': 'unavailable', 'usHeatmap': 'unavailable',
                         'crowdPoll': 'local-only', 'adjustedPrices': 'unavailable'},
            'methodology': {'prices': 'TWSE 官方未還原收盤價；均線/突破為未還原研究值，非含息報酬或回測。',
                            'institutional': '外陸資（不含外資自營商）+投信+自營商（自行+避險）=官方合計；單位股。',
                            'margin': '融資交易單位×1000為股；使用率=今日融資餘額/次一營業日限額，非今日官方使用率。',
                            'futures': 'TX 官方各到期月份合計，OpenInterest(Net)=Long−Short，單位口。',
                            'credit': 'HYG/SHY 還原權息價，1−189交易日含當日百分位；截圖燈號待還原。'}}


def record_failure(data_dir, now, error):
    """Keep last verified values while publishing an explicit integration failure."""
    old = read_json(data_dir / 'market.json')
    if not old or old.get('schemaVersion') != 2:
        old = {'schemaVersion': 2, 'mode': 'unavailable', 'asOf': None, 'source': '等待官方資料',
               'universe': '尚未載入', 'sources': {}, 'stocks': [], 'indexHistory': [], 'futures': [],
               'creditHistory': [], 'creditRule': read_json(ROOT / 'config/credit-rule.json')}
    old['generatedAt'] = now.astimezone(TPE).isoformat(timespec='seconds')
    message = f'資料整合失敗，保留前次成功觀察：{error}'
    old['sources']['pipeline'] = {'name': '整體資料合約', 'asOf': None, 'status': 'error', 'error': message}
    prior_quote = old['sources'].get('quotes', {'name': SOURCES['quotes'][0], 'asOf': None})
    old['sources']['quotes'] = {**prior_quote, 'status': 'error', 'error': message,
                                'lastAttemptAt': old['generatedAt']}
    validate(old)
    report = {'generatedAt': old['generatedAt'], 'asOf': old['asOf'], 'mode': old['mode'],
              'stockCount': len(old['stocks']), 'quoteDays': len(old.get('quoteSessions', [])),
              'sources': old['sources'], 'warnings': [message], 'freshCritical': False}
    write_json(data_dir / 'market.json', old)
    write_json(data_dir / 'quality.json', report)
    write_json(data_dir / 'source-state.json', {'sources': old['sources']})
    write_json(data_dir / 'runs' / f"{now.astimezone(TPE).strftime('%Y-%m-%dT%H%M%S')}.json", report)
    print(message, file=sys.stderr)
    return 2


def run(data_dir=ROOT / 'data', strict=False, credit_file=None, now=None):
    data_dir = Path(data_dir)
    now = now or datetime.now(TPE)
    state = read_json(data_dir / 'source-state.json', {})
    sources = state.get('sources', {})
    sources.pop('pipeline', None)
    cal = collect(data_dir, sources, 'calendar', lambda raw: (max(r['date'] for r in calendar_rows(raw)), calendar_rows(raw)), now)
    calendar = cal['rows'] if cal else []
    collect(data_dir, sources, 'companies', parsers.companies, now)
    q = collect(data_dir, sources, 'quotes', parsers.quotes, now)
    collect(data_dir, sources, 'tpexCompanies', parsers.tpex_companies, now)
    collect(data_dir, sources, 'tpexQuotes', parsers.tpex_quotes, now)
    collect(data_dir, sources, 'index', parsers.index, now)
    collect(data_dir, sources, 'indexHistory', parsers.index_history, now)
    if q:
        d = q['date']
        collect(data_dir, sources, 'institutional', lambda raw: parsers.t86(raw, d), now,
                {'date': d.replace('-', ''), 'selectType': 'ALLBUT0999', 'response': 'json'})
        collect(data_dir, sources, 'margin', lambda raw: parsers.margin(raw, d), now,
                {'date': d.replace('-', ''), 'selectType': 'ALL', 'response': 'json'})
    collect(data_dir, sources, 'futures', parsers.futures, now)
    if cal:
        sources['calendar']['status'] = 'fresh' if any(r['date'][:4] == str(now.astimezone(TPE).year) for r in calendar) else 'unknown'
    try:
        credit = import_credit(credit_file, sources, now)
        payload = build(data_dir, sources, calendar, credit, now)
        from .research import integrate
        payload = integrate(payload, data_dir)
        validate(payload)
    except Exception as exc:
        return record_failure(data_dir, now, exc)
    report = {'generatedAt': payload['generatedAt'], 'asOf': payload['asOf'], 'mode': payload['mode'],
              'stockCount': len(payload['stocks']), 'quoteDays': len(payload['quoteSessions']),
              'sources': payload['sources'], 'warnings': ['信用燈號原始規則待確認', 'T86 公開轉載授權待核實，預設停用', '未還原價格，非含息績效或回測'],
              'freshCritical': all(sources.get(k, {}).get('status') == 'fresh' for k in ('quotes', 'companies', 'tpexQuotes', 'tpexCompanies'))}
    # Validation precedes the single atomic market replacement. A failure never falsifies observation dates.
    write_json(data_dir / 'market.json', payload)
    write_json(data_dir / 'quality.json', report)
    write_json(data_dir / 'source-state.json', {'sources': sources})
    write_json(data_dir / 'runs' / f"{now.astimezone(TPE).strftime('%Y-%m-%dT%H%M%S')}.json", report)
    print(json.dumps({k: report[k] for k in ('asOf', 'stockCount', 'quoteDays', 'freshCritical')}, ensure_ascii=False))
    return 2 if payload['mode'] != 'live' or strict and not report['freshCritical'] else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--strict', action='store_true', help='Nonzero exit when critical modules are stale or failed')
    ap.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    ap.add_argument('--credit-file', type=Path)
    args = ap.parse_args()
    sys.exit(run(args.data_dir, args.strict, args.credit_file))
