"""Canonical dates and unambiguous JSON for evidence, with no trust claim."""
from datetime import date
import json
import re
from urllib.parse import urlencode, urlsplit, parse_qsl


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('date must be YYYY-MM-DD')
    return date.fromisoformat(value)


def unique_json(body):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON field: ' + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('non-finite JSON constant: ' + value)

    return json.loads(body, object_pairs_hook=unique, parse_constant=invalid_constant)


def twse_urls(session):
    month = iso_date(session).strftime('%Y%m01')
    return {
        'ohlc': 'https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?' +
                urlencode({'response': 'json', 'date': month}),
        'turnover': 'https://www.twse.com.tw/exchangeReport/FMTQIK?' +
                    urlencode({'response': 'json', 'date': month}),
    }


RWD_SOURCE_PATHS = {
    'ohlc': '/rwd/zh/TAIEX/MI_5MINS_HIST',
    'turnover': '/rwd/zh/afterTrading/FMTQIK',
}
LEGACY_SOURCE_PATHS = {
    'ohlc': '/indicesReport/MI_5MINS_HIST',
    'turnover': '/exchangeReport/FMTQIK',
}


def official_source_url(session, kind, url, *, rwd_session_only=False):
    """Allow only reviewed TWSE routes with exact session or month queries."""
    day = iso_date(session).strftime('%Y%m%d')
    month = day[:6] + '01'
    if not isinstance(url, str) or not re.fullmatch(r'[!-~]+', url) or '#' in url:
        return False
    try:
        parsed = urlsplit(url)
        fields = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    if (parsed.scheme != 'https' or parsed.netloc != 'www.twse.com.tw' or
            len(fields) != 2 or set(key for key, _ in fields) != {'date', 'response'}):
        return False
    query = dict(fields)
    if query['response'] != 'json':
        return False
    if parsed.path == RWD_SOURCE_PATHS.get(kind):
        allowed_dates = (day,) if rwd_session_only else (month, day)
        return query['date'] in allowed_dates
    return (not rwd_session_only and parsed.path == LEGACY_SOURCE_PATHS.get(kind)
            and query['date'] == month)


def verify_source_endpoints(session, kind, requested, effective, *, rwd_session_only=False):
    if not official_source_url(session, kind, requested, rwd_session_only=rwd_session_only):
        raise ValueError('source request endpoint or query differs from approved TWSE routes')
    if not official_source_url(session, kind, effective, rwd_session_only=rwd_session_only):
        raise ValueError('source effective endpoint or query differs from approved TWSE routes')
