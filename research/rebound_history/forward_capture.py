"""Manual, no-schedule, no-cost prospective TWSE raw observation capture.

All source bytes stay outside the Git tree. Nothing here is a PIT-approved
trading signal; each saved response has a retrieval-time receipt and SHA256.
"""
import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import json
import re

from pit_guard import FROZEN_END, prospective_gate, verify_receipt
from series import price_month

MAX_BYTES=8_000_000


def source_urls(session):
    day=date.fromisoformat(session)
    if day<=FROZEN_END:
        raise ValueError('future capture must be after frozen historical period')
    month=day.strftime('%Y%m01')
    return {
        'ohlc':'https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?'+urlencode({'response':'json','date':month}),
        'turnover':'https://www.twse.com.tw/exchangeReport/FMTQIK?'+urlencode({'response':'json','date':month}),
    }


def fetch_official(url):
    started=datetime.now(timezone.utc)
    with urlopen(Request(url,headers={'User-Agent':'Rebound study manual PIT observation/1.0'}),timeout=20) as response:
        final=response.url
        if (response.status!=200 or urlsplit(final).scheme!='https' or
                urlsplit(final).hostname!='www.twse.com.tw'):
            raise ValueError('official source redirect/status check failed')
        body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:
            raise ValueError('response too large')
        receipt={
            'status':response.status,'url':url,'effective_url':final,
            'started_at_utc':started.isoformat(),
            'completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'http_date':response.headers.get('Date'),
            'last_modified':response.headers.get('Last-Modified'),
            'sha256':sha256(body).hexdigest(),'bytes':len(body),
            'official_published_at':None,
        }
    return body,receipt


def collect(root,session,next_session,frozen_sha,fetcher=fetch_official,frozen_archive=None):
    if not re.fullmatch('[a-f0-9]{64}',frozen_sha):
        raise ValueError('must supply exact frozen-rule archive SHA256')
    day=date.fromisoformat(session)
    next_day=date.fromisoformat(next_session)
    if day<=FROZEN_END or next_day<=day or (next_day-day).days>15:
        raise ValueError('invalid session or next-session date')
    repo=Path(__file__).resolve().parents[2]
    root=Path(root).resolve()
    if (repo/'.github').exists() and (root==repo or repo in root.parents):
        raise ValueError('private raw capture cannot be stored inside public repository')
    archive_verified=False
    if frozen_archive is not None:
        archive=Path(frozen_archive)
        if not archive.is_file() or sha256(archive.read_bytes()).hexdigest()!=frozen_sha:
            raise ValueError('frozen archive bytes do not match pinned hash')
        archive_verified=True
    sources={}
    for kind,url in source_urls(session).items():
        body,receipt=fetcher(url)
        _,finished,legacy=verify_receipt(receipt,body)
        if legacy or receipt['url']!=url:
            raise ValueError('source receipt is incomplete or mismatched')
        rows=price_month(body,session[:7],kind)
        if day not in rows:
            raise ValueError('requested session absent from '+kind)
        sources[kind]=(body,receipt,rows[day],finished)
    price_close=sources['ohlc'][2]['close']
    if price_close!=sources['turnover'][2]['close']:
        raise ValueError('two TWSE official reports disagree on close')
    last_seen=max(x[3] for x in sources.values()).isoformat()
    gate=prospective_gate(session,next_session,last_seen,anchored=False,
                          crosschecked=True,frozen=archive_verified)
    gate.update({
        'index_close':price_close,
        'turnover_ntd':sources['turnover'][2]['turnover'],
        'frozen_rule_archive_sha256':frozen_sha,
        'frozen_rule_archive_bytes_verified':archive_verified,
        'calendar_verified_independently':False,
        'publication_timestamp_verified':False,
        'signal_frozen_before_outcome':False,
        'outcome_matured':False,
        'note':'Local retrieval time is not original publication time. No independent trusted timestamp anchor. Always PIT_BLOCKED.',
    })
    target=root/session/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                         +'-'+token_hex(4))
    target.mkdir(parents=True,exist_ok=False)
    for kind,(body,receipt,_,_) in sources.items():
        (target/(kind+'.body')).write_bytes(body)
        (target/(kind+'.receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    (target/'status.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2)+'\n')
    return target,gate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_root',type=Path)
    p.add_argument('session',help='confirmed TWSE session YYYY-MM-DD')
    p.add_argument('next_session',help='independently checked next TWSE session YYYY-MM-DD')
    p.add_argument('frozen_rule_archive_sha256')
    p.add_argument('--frozen-archive',type=Path,help='optional reviewed local ZIP, matched by exact SHA256')
    a=p.parse_args()
    path,gate=collect(a.private_root,a.session,a.next_session,a.frozen_rule_archive_sha256,frozen_archive=a.frozen_archive)
    print(json.dumps({'saved_to':str(path),'status':gate['status'],'pit_qualified':False},
                     ensure_ascii=False))


if __name__=='__main__':
    main()
