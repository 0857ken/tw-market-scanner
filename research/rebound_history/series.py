"""Strictly parse and reconcile saved official market reports."""
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import io
from html.parser import HTMLParser
import json
import zipfile

from capture import END, START, STUDY, jobs

PRICE = ['日期','開盤指數','最高指數','最低指數','收盤指數']
TURN = ['日期','成交股數','成交金額','成交筆數','發行量加權股價指數','漲跌點數']
MARGIN = ['項目','買進','賣出','現金(券)償還','前日餘額','今日餘額']


def sha(body):
    return hashlib.sha256(body).hexdigest()


def number(value):
    try:
        result = Decimal(str(value).strip().replace(',', ''))
    except InvalidOperation as exc:
        raise ValueError('invalid numeric field') from exc
    if not result.is_finite():
        raise ValueError('nonfinite number')
    return result


def integer(value):
    result = number(value)
    if result != int(result):
        raise ValueError('expected integral value')
    return int(result)


def roc(value):
    y, m, d = (int(v) for v in value.split('/'))
    return date(y + 1911, m, d)


def price_month(body, tag, kind):
    obj = json.loads(body)
    fields = PRICE if kind == 'ohlc' else TURN
    if obj.get('stat') != 'OK' or obj['date'][:6] != tag.replace('-', '') or obj['fields'] != fields:
        raise ValueError('wrong month, status or fields')
    rows = {}
    for line in obj['data']:
        if len(line) != len(fields):
            raise ValueError('unexpected row width')
        d = roc(line[0])
        if d.isoformat()[:7] != tag or d in rows:
            raise ValueError('unexpected or duplicate trade date')
        if kind == 'ohlc':
            o, h, l, c = map(number, line[1:])
            if not 0 < l <= min(o,c) <= max(o,c) <= h:
                raise ValueError('invalid OHLC bounds')
            rows[d] = {'open':float(o),'high':float(h),'low':float(l),'close':float(c)}
        else:
            t, c = integer(line[2]), number(line[4])
            if t <= 0 or c <= 0:
                raise ValueError('invalid index or turnover')
            rows[d] = {'close':float(c),'turnover':t}
    if not rows or list(rows) != sorted(rows):
        raise ValueError('empty or unordered rows')
    return rows


def calendar_year(body, tag):
    obj = json.loads(body)
    year=int(tag)
    if obj.get('fields') != ['日期','名稱','說明'] or str(obj.get('queryYear')) not in (tag,str(year-1911)):
        raise ValueError('calendar response year or schema does not match request')
    days={}
    for iso,name,reason in obj['data']:
        d=date.fromisoformat(iso)
        if d.year!=year or d in days:
            raise ValueError('calendar wrong year or duplicate')
        if '開始交易' not in name and '最後交易' not in name:
            days[d]=(name,reason)
    return days



class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.current = []
        elif tag in ('td','th') and self.current is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.current.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.current is not None:
            self.rows.append(self.current)
            self.current = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def annual_counts(body):
    parser = TableRows()
    parser.feed(body.decode('utf-8-sig'))
    years = [str(y) for y in range(2021, 2026)]
    rows = [r for r in parser.rows if len(r) == 8 and r[0] in years and r[1].isdigit()]
    result = {r[0]: int(r[1]) for r in rows}
    if len(rows) != len(years) or list(result) != years or not all(200 <= v <= 265 for v in result.values()):
        raise ValueError('unexpected TWSE Fact Book table')
    return result

def margin_day(body, tag):
    obj=json.loads(body)
    if obj.get('stat')!='OK' or obj.get('date')!=tag.replace('-',''):
        raise ValueError('margin report date/status mismatch')
    tables=[t for t in obj.get('tables',[]) if t.get('fields')==MARGIN]
    if len(tables)!=1:
        raise ValueError('market monetary summary missing or ambiguous')
    entries={row[0]:[integer(x) for x in row[1:]] for row in tables[0]['data']}
    if len(entries)!=len(tables[0]['data']):
        raise ValueError('duplicate margin summary rows')
    buy,sell,repaid,prev,now=entries['融資金額(仟元)']
    shares=entries['融券(交易單位)']
    if min(buy,sell,repaid)<0 or min(prev,now)<=0 or shares[-1]<0:
        raise ValueError('invalid balance')
    return {'margin_100m':now/100_000,'margin_today_thousand':now,'margin_previous_thousand':prev,
            'margin_identity_delta_thousand':now-(prev+buy-sell-repaid),'short_balance_trade_units':shares[-1]}


def futures_year(body, tag):
    try:
        content=body.decode('utf-8-sig')
    except UnicodeDecodeError:
        content=body.decode('cp950')
    raw=csv.DictReader(io.StringIO(content))
    wanted={'日期','商品名稱','身份別','多方未平倉口數','空方未平倉口數','多空未平倉口數淨額'}
    if not wanted <= set(raw.fieldnames or []):
        raise ValueError('futures CSV missing required fields')
    rows={}
    for row in raw:
        if row['商品名稱']!='臺股期貨' or row['身份別']!='外資及陸資':
            continue
        raw_date=row['日期'].replace('/','-')
        d=date.fromisoformat(raw_date if '-' in raw_date else f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}')
        if d.year!=int(tag) or d in rows:
            raise ValueError('futures unexpected/duplicate session')
        long=integer(row['多方未平倉口數']); short=integer(row['空方未平倉口數'])
        if min(long,short)<0 or long-short!=integer(row['多空未平倉口數淨額']):
            raise ValueError('invalid open-interest identity')
        rows[d]=short-long
    if not rows:
        raise ValueError('no TXF foreign open-interest rows')
    return rows


def frozen(archive, expected):
    if sha(archive.read_bytes())!=expected:
        raise ValueError('original archive hash mismatch')
    with zipfile.ZipFile(archive) as z:
        freeze=json.loads(z.read('data/r25_frozen_rules.json'))
        for name, digest in freeze['files_sha256'].items():
            if sha(z.read(name))!=digest:
                raise ValueError(f'frozen member hash mismatch: {name}')
        source=z.read('tools/backtest.py')
        rules={'__file__':'frozen/tools/backtest.py','__name__':'_verified_frozen_rules'}
        exec(compile(source,'frozen/tools/backtest.py','exec'),rules)
        if set(rules['LABELS'])!=set(freeze['signal_keys']) or len(rules['LABELS'])!=15:
            raise ValueError('frozen signal inventory mismatch')
    return rules, freeze


def load_source(root, kind, tag):
    path=root/kind/tag
    receipt=json.loads(path.with_suffix('.json').read_bytes())
    body=path.with_suffix('.body').read_bytes()
    if receipt['status']!=200 or sha(body)!=receipt['sha256'] or len(body)!=receipt['bytes']:
        raise ValueError('source integrity check failed')
    return body


def assemble(root, excluded_margin_dates=()):
    errors=[]
    groups={}
    parsers={'ohlc':lambda b,t:price_month(b,t,'ohlc'),'turnover':lambda b,t:price_month(b,t,'turnover'),
             'calendar':calendar_year,'futures':futures_year}
    for kind,parser in parsers.items():
        groups[kind]={}
        for _,tag,urls in jobs(kind):
            try:
                groups[kind][tag]=parser(load_source(root,kind,tag),tag)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                errors.append({'source':kind,'key':tag,'url':urls[0],'reason':str(exc)})
    rows=[]; day_audit=[]; segment=0
    d=START
    margins={}
    while d<=END:
        iso=d.isoformat()
        tag=iso[:7]
        prices=groups['ohlc'].get(tag,{})
        turnover=groups['turnover'].get(tag,{})
        calendar=groups['calendar'].get(str(d.year))
        future=groups['futures'].get(str(d.year),{}).get(d)
        p,t=prices.get(d),turnover.get(d)
        margin=None
        if p:
            try:
                margin=margin_day(load_source(root,'margin',iso),iso)
                margins[d]=margin
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if (root/'margin'/iso).with_suffix('.json').exists():
                    errors.append({'source':'margin','key':iso,'reason':str(exc)})
        closed=calendar is not None and d in calendar
        # Quarantine unexplained report arithmetic and any dates under a separate source review.
        margin_admitted=bool(margin and not margin['margin_identity_delta_thousand']
                             and iso not in excluded_margin_dates)
        if p and t and p['close']==t['close'] and not closed:
            state='SESSION_TWO_OFFICIAL_REPORTS'
            rows.append({'date':iso,**p,'turnover':t['turnover'],
                         'margin_100m':margin['margin_100m'] if margin_admitted else None,
                         'foreign_net_100m':None,'foreign_futures_net_short':future,'segment':segment})
        elif p or t or (d.weekday()<5 and (tag not in groups['ohlc'] or tag not in groups['turnover'])):
            state='UNALIGNED_OR_MISSING_REPORT'
            segment+=1
        elif closed:
            state='OFFICIAL_CALENDAR_CLOSED'
        elif d.weekday()>=5:
            state='WEEKEND_NO_TRADE_IN_REPORTS'
        else:
            state='NO_TRADE_IN_BOTH_REPORTS_CALENDAR_UNCONFIRMED'
        day_audit.append({'date':iso,'research_period':d>=STUDY,'state':state,
                          'official_calendar_year_verified':calendar is not None,
                          'ohlc':bool(p),'turnover':bool(t),'close_match':p['close']==t['close'] if p and t else None,
                          'margin_source_present':margin is not None,'margin':margin_admitted,
                          'foreign_cash':False,'futures':future is not None})
        d+=timedelta(days=1)
    return rows, day_audit, errors, margins
