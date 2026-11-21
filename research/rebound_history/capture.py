"""Manual collection from public official reports. Raw and derived files stay outside Git."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

TWSE = 'https://www.twse.com.tw'
TAIFEX = 'https://www.taifex.com.tw'
START, STUDY, END = date(2021,1,1), date(2021,11,16), date(2026,11,13)


def url(host, path, **params):
    return host + path + '?' + urlencode(params, safe='/')


def jobs(series, dates=()):
    if series == 'margin':
        for d in dates:
            yield series, d.isoformat(), [url(TWSE, '/exchangeReport/MI_MARGN', response='json',
                                            date=d.strftime('%Y%m%d'), selectType='MS')]
        return
    for y in range(START.year, END.year + 1):
        if series == 'calendar':
            yield series, str(y), [url(TWSE, '/holidaySchedule/holidaySchedule', response='json', date=f'{y}0101')]
        if series == 'futures':
            end = END if y == END.year else date(y,12,31)
            yield series, str(y), [url(TAIFEX, '/cht/3/futContractsDateDown', queryStartDate=f'{y}/01/01',
                                      queryEndDate=end.strftime('%Y/%m/%d'), commodityId='TXF')]
        if series not in ('ohlc', 'turnover'):
            continue
        path = '/indicesReport/MI_5MINS_HIST' if series == 'ohlc' else '/exchangeReport/FMTQIK'
        for m in range(1, (END.month if y == END.year else 12) + 1):
            yield series, f'{y}-{m:02}', [url(TWSE, path, response='json', date=f'{y}{m:02}01')]

    if series == 'futures':
        # The public historical window may exclude almost all of 2023.
        yield 'futures_alternates', '2023-tail', [url(TAIFEX, '/cht/3/futContractsDateDown',
            queryStartDate='2023/11/17', queryEndDate='2023/12/31', commodityId='TXF')]


def capture(root, job):
    series, tag, urls = job
    path = root / series / tag
    path.parent.mkdir(parents=True, exist_ok=True)
    body_path, receipt_path = path.with_suffix('.body'), path.with_suffix('.json')
    if body_path.is_file() and receipt_path.is_file():
        old = json.loads(receipt_path.read_text())
        if hashlib.sha256(body_path.read_bytes()).hexdigest() == old.get('sha256') and old.get('status') == 200:
            return series, tag, 200
    attempts = []
    for request_url in urls:
        for attempt in range(2):
            started = datetime.now(timezone.utc)
            try:
                try:
                    response = urlopen(Request(request_url, headers={'User-Agent':'TWSE historical research/1.0'}), timeout=12)
                except HTTPError as exc:
                    response = exc
                with response:
                    status, final_url = response.status, response.url
                    if urlsplit(final_url).hostname != urlsplit(request_url).hostname:
                        raise ValueError(f'unexpected redirect: {urlsplit(final_url).hostname}')
                    body = response.read(8_000_001)
                    if len(body) > 8_000_000:
                        raise ValueError('unexpected size')
                    receipt = {'url':request_url,'effective_url':final_url,'status':status,
                               'started_at_utc':started.isoformat(),
                               'completed_at_utc':datetime.now(timezone.utc).isoformat(),
                               'http_date':response.headers.get('Date'),
                               'last_modified':response.headers.get('Last-Modified'),
                               'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),
                               'official_published_at':None}
                    if status == 200:
                        body_path.write_bytes(body)
                        receipt['prior_attempts']=attempts
                        receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
                        return series, tag, status
                    attempts.append(receipt)
                    if status not in (429, 500, 502, 503, 504):
                        break
                    if status == 429:
                        break
            except (OSError, ValueError) as exc:
                attempts.append({'url':request_url,'error':str(exc),'started_at_utc':started.isoformat(),
                                 'completed_at_utc':datetime.now(timezone.utc).isoformat()})
            sleep(1)
    if attempts and 'sha256' in attempts[-1]:
        body_path.write_bytes(body)
    receipt_path.write_text(json.dumps({'status':None,'attempts':attempts},indent=2)+'\n')
    return series, tag, None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('series', nargs='+',choices=('ohlc','turnover','calendar','futures','margin'))
    parser.add_argument('--sessions', type=Path, help='newline-delimited ISO official trading dates')
    parser.add_argument('--workers', type=int, default=6, choices=range(1,9))
    args=parser.parse_args()
    dates=[date.fromisoformat(x) for x in args.sessions.read_text().splitlines()] if args.sessions else []
    if 'margin' in args.series and (not dates or dates != sorted(set(dates)) or
                                    any(d < START or d > END for d in dates)):
        parser.error('margin needs unique sorted in-range official session dates')
    groups=[j for series in args.series for j in jobs(series,dates)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(lambda job: capture(args.root,job),groups):
            print(*row,flush=True)


if __name__=='__main__':
    main()
