"""Stage 3B price layers. No historical network fetch and no inferred adjustment factors.

Current rosters are NOT point-in-time membership archives. Missing lifecycle/adjustment
approval is represented explicitly, never inferred from a disappearing quote.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
from .common import ROOT, read_json, write_json

MARKETS = ('TWSE', 'TPEx')
MODULES = {'TWSE': ('companies', 'quotes'), 'TPEx': ('tpexCompanies', 'tpexQuotes')}


def ordinary(symbol, name):
    return isinstance(symbol, str) and len(symbol) == 4 and symbol.isascii() and symbol.isdigit() and not symbol.startswith('00') and '-DR' not in name.upper()


def member_on(stock, day):
    life = stock.get('lifecycle', {})
    start, end = life.get('listedOn'), life.get('delistedOn')
    return (not start or start <= day) and (not end or day < end)


def suspended_on(stock, day):
    return any(r['from'] <= day and (r.get('to') is None or day < r['to']) for r in stock.get('lifecycle', {}).get('suspensions', []))


def checked_import(path, kind, approvals=None):
    """Local import only. Rights approval is pinned OUTSIDE the supplied data by file SHA.

    The registry is code-reviewed; a file's own 'verified' flag grants no rights.
    A valid historical grant must explicitly include public redistribution.
    """
    approvals = approvals if approvals is not None else read_json(ROOT/'config/research-approvals.json')
    body = Path(path).read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    grant = approvals.get(kind, {}).get(digest)
    if not grant or grant.get('status') != 'reviewed' or grant.get('permitsRedistribution') is not True or not grant.get('evidence', '').startswith('https://'):
        raise ValueError('No independently reviewed file/dataset redistribution approval')
    data = json.loads(body)
    if data.get('kind') != kind or data.get('version') != grant.get('version'):
        raise ValueError('Import kind/version does not match approval')
    return data, digest


def adjusted_prices(raw_rows, factors, *, method, version):
    """Apply independently verified backward factors, NOT dividend reference prices.

    Does not confer approval: publication additionally needs checked_import and a
    reviewed version. Multipliers apply strictly before their effective session.
    Total-return factors must already include the documented reinvestment convention.
    """
    if method not in ('backward-price', 'backward-total-return') or not version:
        raise ValueError('Explicit adjustment method/version required')
    if any(f.get('kind') == 'ex-reference-price' for f in factors):
        raise ValueError('Ex-right reference prices are not adjustment factors')
    dates = [f['effectiveDate'] for f in factors]
    if dates != sorted(set(dates)) or any(not isinstance(f.get('factor'), (float, int)) or isinstance(f['factor'], bool) or not math.isfinite(f['factor']) or f['factor'] <= 0 for f in factors):
        raise ValueError('Positive, unique ordered factors required')
    result = []
    for row in raw_rows:
        factor = math.prod(f['factor'] for f in factors if row['date'] < f['effectiveDate'])
        result.append({**row, 'adjustedClose': row['rawClose'] * factor if row['rawClose'] is not None else None,
                       'adjustmentFactor': factor, 'adjustmentVersion': version})
    return result


def snapshots(root, module):
    return [read_json(p) for p in sorted((Path(root)/'raw').glob(module+'_*.json'))][-300:]


def integrate(payload, root):
    """Merge only licensed current snapshots; no network I/O. Old observations retained."""
    out = copy.deepcopy(payload)
    prior = {(s.get('market', 'TWSE'), s['symbol']): s for s in payload['stocks']}
    stocks, markets = [], {}
    quote_dates = [s.get('asOf') for k,s in out['sources'].items() if k in ('quotes','tpexQuotes') and s.get('asOf')]
    as_of = max(quote_dates, default=out.get('asOf'))
    approved_history=[]
    for path in sorted((Path(root)/'history').glob('*.json')):
        archive,digest=checked_import(path,'histories')
        approved_history.extend({**r,'sourceVersion':digest} for r in archive['rows'])
    for market, (roster_module, quote_module) in MODULES.items():
        rosters, quotes = snapshots(root, roster_module), snapshots(root, quote_module)
        roster = rosters[-1] if rosters else None
        profiles = roster['rows'] if roster else [dict(symbol=s['symbol'],name=s['name'],date=s.get('profileAsOf',payload.get('asOf')),sector=s.get('sector','未分類'),sectorCode=s.get('sectorCode'),issuedShares=None) for (m,_),s in prior.items() if m==market]
        profiles = [p for p in profiles if ordinary(p['symbol'],p['name'])]
        if len({p['symbol'] for p in profiles}) != len(profiles): raise ValueError('Duplicate company roster')
        source = out['sources'].get(quote_module, {})
        day = source.get('asOf')
        observed = sorted(set(s['date'] for s in quotes) | {r['date'] for (m,_),s in prior.items() if m==market for r in s['history']})
        # A calendar supplied for TWSE is not silently certified as a TPEx calendar.
        # Only observed sessions are known for TPEx until its own calendar is verified.
        sessions = sorted(set(payload.get('quoteSessions', []) if market=='TWSE' else []) | set(observed))[-300:]
        history_rows=[r for r in approved_history if r['market']==market and r['date']<=as_of]
        sessions=sorted(set(sessions)|{r['date'] for r in history_rows})[-300:]
        by_symbol = {}
        for r in history_rows:
            by_symbol.setdefault(r['symbol'],{})[r['date']]={**r,'close':r['rawClose']}
        versions = {}
        for snap in quotes:
            versions[snap['date']] = snap['sha256']
            for row in snap['rows']:
                by_symbol.setdefault(row['symbol'], {})[row['date']] = row
        inst_by_symbol,events_by_symbol={},{}
        if market=='TPEx':
            for snap in snapshots(root,'tpexInstitutional'):
                for r in snap['rows']:inst_by_symbol.setdefault(r['symbol'],[]).append({k:v for k,v in r.items() if k!='symbol'})
            for snap in snapshots(root,'tpexEvents'):
                for r in snap['rows']:events_by_symbol.setdefault(r['symbol'],[]).append({**r,'source':'tpexEvents','sourceVersion':snap['sha256']})
        for profile in sorted(profiles,key=lambda p:p['symbol']):
            symbol = profile['symbol']
            stock = copy.deepcopy(prior.get((market,symbol), {}))
            rows = {r['date']:r for r in stock.get('history', [])}
            rows.update(by_symbol.get(symbol, {}))
            hist = []
            for d in sessions:
                if profile.get('listedOn') and d < profile['listedOn']: continue
                r = rows.get(d, {})
                close = r.get('rawClose',r.get('close'))
                hist.append({'date':d,'close':close,'rawClose':close,'adjustedClose':None,'adjustmentVersion':None,
                             'volumeShares':r.get('volumeShares'),'changeAmount':r.get('changeAmount'),
                             'status':r.get('status', 'ok' if close is not None else 'missing'),
                             'source':quote_module,'sourceVersion':r.get('sourceVersion') or versions.get(d) or source.get('sha256'), 'market':market})
            stock.update(symbol=symbol,name=profile['name'],market=market,securityId=f'{market}:{symbol}',securityType='ordinary',
                         sector=profile.get('sector','未分類'),sectorCode=profile.get('sectorCode'),priceBasis='unadjusted',profileAsOf=profile['date'],
                         history=hist,events=[],eventCoverage={'status':'unknown','from':None,'to':None},
                         adjustment={'status':'unavailable','method':None,'version':None},
                         lifecycle={'listedOn':profile.get('listedOn'),'delistedOn':None,'suspensions':[],
                                    'rosterAsOf':profile['date'],'status':'current-roster-only','pointInTimeVerified':False,'source':roster_module})
            if market=='TPEx':
                stock.update(institutional=inst_by_symbol.get(symbol,[]),margin=None)
                stock['events']=events_by_symbol.get(symbol,[])
            stock.setdefault('institutional',[])
            stock.setdefault('margin',None)
            latest=next((r for r in hist if r['date']==as_of),None)
            shares=profile.get('issuedShares')
            stock['marketCapM']=latest['rawClose']*shares/1e6 if latest and latest['rawClose'] and shares else None
            stock['marketCapAsOf']=as_of if stock['marketCapM'] is not None else None
            stocks.append(stock)
        markets[market] = {'asOf':day,'rosterAsOf':roster['date'] if roster else None,'rosterCount':len(profiles),
                           'sessions':sessions,'targetSessions':300,'calendarStatus':'partial',
                           'lifecycleStatus':'current-roster-only','quoteSource':quote_module,
                           'institutionalSessions':[r['date'] for r in snapshots(root,'tpexInstitutional')] if market=='TPEx' else payload.get('institutionalSessions',[]),
                           'note':'僅確認已觀測日期；完整市場交易日與歷史成員事件尚待驗證'}
        if market=='TPEx' and quote_module not in out['sources']:
            out['sources'][quote_module]={'name':'TPEx 上櫃收盤行情','asOf':None,'status':'unavailable','reason':'尚無通過驗證的快照'}
    out.update(researchVersion=1,stocks=stocks,asOf=as_of,quoteSessions=markets['TWSE']['sessions'],research={'targetSessions':300,'markets':markets},
               universe='TWSE 上市／TPEx 上櫃普通股；當期公司名單，非完整歷史母體',
               universeMeta={'pointInTimeHistory':False,'priceBasis':'separate-raw-adjusted','rosterCount':len(stocks),'loadedCount':sum(bool(s['history']) for s in stocks)})
    out['source']='TWSE / TPEx / TAIFEX 官方開放資料（盤後）'
    out['methodology']['prices']='未還原與還原價獨立欄位；還原資料未驗證時不回退至原價。暫行未還原突破須完整日曆及無公司事件窗口證據。'
    return out


def validate_research(payload):
    """Additional fail-closed contract for Stage 3B. Approved adjustment catalog empty."""
    if payload.get('researchVersion') != 1: raise ValueError('Unsupported research version')
    from .schema import valid_date
    markets = payload['research']['markets']
    if set(markets) != set(MARKETS): raise ValueError('Both market coverage records required')
    for market, meta in markets.items():
        if meta.get('targetSessions') != 300 or meta.get('calendarStatus') not in ('partial','verified'):
            raise ValueError('Calendar coverage required')
        dates = meta['sessions']
        if not isinstance(dates,list):raise ValueError('Sessions must be an array')
        for d in dates: valid_date(d)
        if dates != sorted(set(dates)) or any(d > payload['asOf'] for d in dates): raise ValueError('Invalid market sessions')
        # No external payload can self-approve a missing calendar/event/adjustment archive.
        if meta['calendarStatus']=='verified': raise ValueError('Verified calendar archive not registered')
    for s in payload['stocks']:
        if s.get('market') not in MARKETS or s.get('securityId') != f"{s['market']}:{s['symbol']}" or s.get('securityType')!='ordinary' or not ordinary(s['symbol'],s['name']):
            raise ValueError('Ordinary security classification required')
        if s.get('priceBasis')!='unadjusted': raise ValueError('Legacy close must remain raw')
        if s.get('adjustment')!={'status':'unavailable','method':None,'version':None}: raise ValueError('Adjustment version not independently approved')
        if s.get('eventCoverage',{}).get('status')!='unknown': raise ValueError('Event archive not independently approved')
        if not isinstance(s.get('lifecycle'),dict) or s['lifecycle'].get('pointInTimeVerified') is not False: raise ValueError('Historical lifecycle not verified')
        life=s['lifecycle']
        if life.get('status')!='current-roster-only' or life.get('source')!=('companies' if s['market']=='TWSE' else 'tpexCompanies'):raise ValueError('Lifecycle provenance missing')
        for key in ('listedOn','delistedOn','rosterAsOf'):
            if life.get(key) is not None: valid_date(life[key])
        if life.get('listedOn') and life.get('delistedOn') and life['listedOn']>=life['delistedOn']:raise ValueError('Invalid lifecycle dates')
        previous_end=''
        for span in life.get('suspensions',[]):
            valid_date(span['from'])
            if span.get('to') is not None:valid_date(span['to'])
            if previous_end is None or span['from']<previous_end or span.get('to') and span['to']<=span['from']:raise ValueError('Invalid suspension interval')
            previous_end=span.get('to')
        for event in s.get('events',[]):
            valid_date(event['date'])
            if event.get('kind')!='ex-reference-price' or event.get('status')!='official-reference-only':raise ValueError('Unverified adjustment event')
        source = 'quotes' if s['market']=='TWSE' else 'tpexQuotes'
        ceiling = payload['sources'].get(source,{}).get('asOf')
        for r in s['history']:
            if 'rawClose' not in r or r['rawClose']!=r['close'] or r.get('adjustedClose') is not None or r.get('adjustmentVersion') is not None:
                raise ValueError('Mixed or unapproved price basis')
            if r.get('market')!=s['market'] or r.get('source')!=source or not isinstance(r.get('sourceVersion'),str) or len(r['sourceVersion'])!=64:
                raise ValueError('Price provenance missing')
            if r['close'] is not None and (not ceiling or r['date']>ceiling): raise ValueError('Price exceeds market source date')
    return payload


def apply_lifecycle(stock, events):
    """Apply reviewed lifecycle events; exits are exclusive, resume dates inclusive.

    A transfer closes only the old market identity. The destination is a separate
    identity with its own history; never splice the two price windows automatically.
    """
    from .schema import valid_date
    s=copy.deepcopy(stock)
    life=s.setdefault('lifecycle',{'listedOn':None,'delistedOn':None,'suspensions':[]})
    previous=''
    for e in events:
        valid_date(e['date'])
        if e['date']<previous: raise ValueError('Lifecycle events must be chronological')
        previous=e['date']
        kind=e['kind']
        if kind=='listed': life['listedOn']=e['date']
        elif kind in ('delisted','transfer-out'): life['delistedOn']=e['date']
        elif kind=='suspend':
            if life.get('suspensions') and life['suspensions'][-1]['to'] is None: raise ValueError('Already suspended')
            life.setdefault('suspensions',[]).append({'from':e['date'],'to':None})
        elif kind=='resume':
            if not life.get('suspensions') or life['suspensions'][-1]['to'] is not None: raise ValueError('No open suspension')
            if e['date']<=life['suspensions'][-1]['from']: raise ValueError('Intraday suspension needs separate timed events')
            life['suspensions'][-1]['to']=e['date']
        else: raise ValueError('Unsupported lifecycle event')
    if life.get('listedOn') and life.get('delistedOn') and life['listedOn']>=life['delistedOn']: raise ValueError('Invalid membership interval')
    return s


def import_history(path, destination, approvals=None):
    """Validated local-file ingestion, disabled until its exact file SHA is approved."""
    from .schema import valid_date, valid_number
    data,digest=checked_import(path,'histories',approvals)
    seen=set()
    for r in data['rows']:
        valid_date(r['date'])
        if r.get('market') not in MARKETS or not ordinary(r.get('symbol'),r.get('name','')): raise ValueError('Invalid historical security')
        key=(r['market'],r['symbol'],r['date'])
        if key in seen: raise ValueError('Duplicate historical row')
        seen.add(key)
        if 'rawClose' not in r or r['rawClose'] is not None and (not valid_number(r['rawClose']) or r['rawClose']<=0): raise ValueError('Invalid raw price')
        if r.get('adjustedClose') is not None: raise ValueError('Adjusted archive requires a separate adjustment approval')
        if r.get('volumeShares') is not None and (not valid_number(r['volumeShares']) or r['volumeShares']<0): raise ValueError('Invalid shares')
    # Preserve original bytes: exact approved version hash must survive persistence.
    target=Path(destination)/'history'/f'{digest}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(Path(path).read_bytes())
    return {'path':str(target),'sha256':digest,'rows':len(data['rows']),'version':data['version']}


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description='Import only a separately approved historical file; never fetch history')
    ap.add_argument('--history-file',type=Path,required=True)
    ap.add_argument('--data-dir',type=Path,default=ROOT/'data')
    args=ap.parse_args()
    print(json.dumps(import_history(args.history_file,args.data_dir)))
