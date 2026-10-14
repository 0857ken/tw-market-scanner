"""Standard-library HTTP, calendar and atomic persistence helpers."""
import hashlib
import json
import math
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TPE = ZoneInfo('Asia/Taipei')
LICENSE = 'https://data.gov.tw/license'
ALLOWED_HOSTS = {'openapi.twse.com.tw', 'www.twse.com.tw', 'openapi.taifex.com.tw', 'www.tpex.org.tw'}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace(',', '').strip())
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def iso_date(value):
    s = str(value).strip().replace('/', '-').replace('.', '-')
    if re.fullmatch(r'\d{7,8}', s):
        s = f'{s[:-4]}-{s[-4:-2]}-{s[-2:]}'
    parts = s.split('-')
    if len(parts) != 3:
        raise ValueError(f'Invalid source date: {value}')
    y, m, d = map(int, parts)
    if y < 1911:
        y += 1911
    return date(y, m, d).isoformat()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    os.replace(tmp, path)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def get_json(url, params=None, attempts=2):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username:
        raise ValueError('Only allowlisted, credential-free official HTTPS endpoints are permitted')
    if params:
        url += '?' + urlencode(params)
    last = None
    for attempt in range(attempts):
        try:
            req = Request(url, headers={'User-Agent': 'TW-Market-Scanner/3.0 (read-only research)', 'Accept': 'application/json'})
            with urlopen(req, timeout=15) as response:
                if urlparse(response.url).hostname not in ALLOWED_HOSTS:
                    raise ValueError('Unexpected redirect')
                body = response.read(20_000_001)
                if len(body) > 20_000_000:
                    raise ValueError('Response exceeds 20 MB limit')
            return json.loads(body), hashlib.sha256(body).hexdigest(), url
        except Exception as exc:
            # Explicit official refusal/rate limiting is terminal; no retry or fallback.
            if isinstance(exc, HTTPError) and exc.code in (403, 429):
                raise
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1)
    raise RuntimeError(f'{parsed.hostname}: {type(last).__name__}: {last}')


def calendar_rows(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError('Empty calendar')
    rows = []
    for r in raw:
        d = iso_date(r['Date'])
        text = str(r.get('Name', '')) + str(r.get('Description', ''))
        # Start/last trading days are events, not holidays. Settlement-only days are closed.
        closed = not any(t in text for t in ('開始交易', '最後交易'))
        rows.append({'date': d, 'closed': closed, 'name': str(r.get('Name', ''))})
    return rows


def expected_session(now, calendar):
    local = now.astimezone(TPE)
    candidate = local.date()
    if (local.hour, local.minute) < (16, 30):
        candidate -= timedelta(days=1)
    years = {int(r['date'][:4]) for r in calendar}
    known = candidate.year in years
    closed = {r['date'] for r in calendar if r['closed']}
    while candidate.weekday() >= 5 or candidate.isoformat() in closed:
        candidate -= timedelta(days=1)
        known = known and candidate.year in years
    return candidate.isoformat(), known


def timestamp():
    return datetime.now(TPE).isoformat(timespec='seconds')
