"""Fail-closed PIT receipt audit. Retrieval time is not original publication time."""
from bisect import bisect_right
from collections import Counter
from datetime import date, datetime, time, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import csv
import io
import json
import re
import zipfile

from evidence_schema import iso_date, unique_json

TZ = ZoneInfo('Asia/Taipei')
HOSTS = {'www.twse.com.tw', 'www.taifex.com.tw'}
SERIES = {'ohlc','turnover','margin','calendar','futures','futures_alternates','official_checks'}
FROZEN_END = date(2026,11,13)


def as_utc(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}T', value):
        raise ValueError('timestamp must have an ISO date and time')
    d = datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError('missing timestamp offset')
    return d.astimezone(timezone.utc)


def verify_receipt(receipt, body, allow_legacy=False):
    if receipt.get('status') != 200 or receipt.get('bytes') != len(body) or receipt.get('sha256') != sha256(body).hexdigest():
        raise ValueError('invalid status or raw SHA256/bytes')
    source = urlsplit(receipt.get('url',''))
    final = urlsplit(receipt.get('effective_url') or '')
    official = source.hostname in HOSTS
    public_manifest = source.hostname == '0857ken.github.io' and source.path == '/tw-market-scanner/release-manifest.json'
    if source.scheme != 'https' or not (official or public_manifest):
        raise ValueError('source URL not approved')
    legacy = not receipt.get('started_at_utc') or not receipt.get('effective_url')
    if legacy and not allow_legacy:
        raise ValueError('legacy receipt cannot establish origin timing')
    if receipt.get('effective_url') and (final.scheme != 'https' or final.hostname != source.hostname):
        raise ValueError('unexpected redirect')
    start = as_utc(receipt['started_at_utc']) if receipt.get('started_at_utc') else None
    finish = as_utc(receipt['completed_at_utc'])
    if start and finish < start:
        raise ValueError('invalid receipt time order')
    return start, finish, legacy


def next_session(observed_dates, day):
    i = bisect_right(observed_dates, day)
    return observed_dates[i] if i < len(observed_dates) else None


def classify(series, tag, completion, dates):
    if series != 'margin':
        return 'NOT_SESSION_SCOPED'
    next_day = next_session(dates, iso_date(tag))
    if next_day is None:
        return 'NEXT_SESSION_UNDOCUMENTED'
    limit = datetime.combine(next_day,time(9),tzinfo=TZ).astimezone(timezone.utc)
    return 'AFTER_NEXT_OPEN' if completion >= limit else 'BEFORE_NEXT_OPEN_UNANCHORED'


def audit_zip(path, pinned_sha):
    raw = Path(path).read_bytes()
    if not re.fullmatch('[a-f0-9]{64}',pinned_sha) or sha256(raw).hexdigest() != pinned_sha:
        raise ValueError('pinned private ZIP SHA256 mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        filenames = archive.namelist()
        if len(filenames) != len(set(filenames)):
            raise ValueError('duplicate ZIP filenames')
        names = set(filenames)
        with archive.open('results/input_series.csv') as file:
            dates = sorted(date.fromisoformat(row['date']) for row in csv.DictReader(io.TextIOWrapper(file,encoding='utf-8-sig')))
        if len(dates) != len(set(dates)):
            raise ValueError('duplicate trading dates')
        records = []
        for name in sorted(names):
            if not (name.startswith('raw/') and name.endswith('.json')):
                continue
            parts=name.split('/')
            if len(parts) != 3 or parts[1] not in SERIES:
                raise ValueError('unexpected raw path')
            series,tag = parts[1],parts[2][:-5]
            body_name = name[:-5]+'.body'
            if body_name not in names:
                raise ValueError('raw body missing')
            receipt = unique_json(archive.read(name))
            started,done,legacy = verify_receipt(receipt,archive.read(body_name),allow_legacy=True)
            records.append({
                'series':series,'tag':tag,
                'started_utc':started.isoformat() if started else None,
                'completed_utc':done.isoformat(),
                'retrieved_utc_day':done.date().isoformat(),
                'raw_sha256':receipt['sha256'],
                'legacy_incomplete_receipt':legacy,
                'timing_classification':'LEGACY_RECEIPT_UNVERIFIED' if legacy else classify(series,tag,done,dates),
                'pit_qualified':False,
                'blocker':'LEGACY_RECEIPT_INCOMPLETE' if legacy else 'HISTORICAL_FIRST_PUBLICATION_TIME_AND_VERSION_UNVERIFIED',
            })
    summary={
        'private_archive_sha256':pinned_sha,
        'receipt_n':len(records),
        'receipt_days_utc':dict(sorted(Counter(r['retrieved_utc_day'] for r in records).items())),
        'timing_classes':dict(sorted(Counter(r['timing_classification'] for r in records).items())),
        'legacy_incomplete_n':sum(r['legacy_incomplete_receipt'] for r in records),
        'pit_qualified_n':0,
        'status':'BLOCKED',
        'caution':'Historical retrieval is not as-of publication. Retrospective session sequence is not independent calendar PIT.',
    }
    return summary,records


def prospective_gate(session,next_session_date,completed_utc,anchored,crosschecked,frozen):
    s,n=iso_date(session),iso_date(next_session_date)
    t=as_utc(completed_utc)
    if s<=FROZEN_END or n<=s or (n-s).days>15:
        raise ValueError('not an approved prospective date pair')
    close=datetime.combine(s,time(13,30),tzinfo=TZ).astimezone(timezone.utc)
    open_=datetime.combine(n,time(9),tzinfo=TZ).astimezone(timezone.utc)
    in_window=close<=t<open_
    candidate=bool(in_window and anchored and crosschecked and frozen)
    return {
        'session':session,'next_session':next_session_date,'completed_utc':t.isoformat(),
        'retrieval_before_next_open':in_window,
        'independent_timestamp_anchor':bool(anchored),
        'crosschecked':bool(crosschecked),
        'frozen_rule_evidence':bool(frozen),
        'prospective_candidate':candidate,
        'pit_qualified':False,
        'status':'CANDIDATE_REVIEW_REQUIRED' if candidate else 'BLOCKED',
    }


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_zip',type=Path)
    p.add_argument('--sha256',required=True)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    summary,records=audit_zip(a.private_zip,a.sha256)
    if a.out:
        repo=Path(__file__).resolve().parents[2]
        output=a.out.resolve()
        if (repo/'.github').exists() and (output==repo or repo in output.parents):
            p.error('no private audit data in public repository')
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists():
            p.error('no overwrite of previous audit')
        output.write_text(json.dumps({'summary':summary,'receipts':records},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
