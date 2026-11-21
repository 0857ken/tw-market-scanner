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


def official_source_url(session, kind, url):
    """Allow only reviewed TWSE routes for the exact observation session.

    RWD OHLC accepts a session-specific daily query or the first day of that
    month; legacy monthly OHLC and turnover accept only first-of-month.
    Query key order may differ, but duplicate/extra keys and redirects to
    unexpected paths are never approved.
    """
    day = iso_date(session).strftime('%Y%m%d')
    month = day[:6] + '01'
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        fields = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    if (parsed.scheme != 'https' or parsed.netloc != 'www.twse.com.tw' or
            parsed.fragment or len(fields) != 2 or
            set(key for key, _ in fields) != {'date', 'response'}):
        return False
    query = dict(fields)
    if query['response'] != 'json':
        return False
    if kind == 'ohlc':
        if parsed.path == '/indicesReport/MI_5MINS_HIST':
            return query['date'] == month
        if parsed.path == '/rwd/zh/TAIEX/MI_5MINS_HIST':
            return query['date'] in (month, day)
    if kind == 'turnover' and parsed.path == '/exchangeReport/FMTQIK':
        return query['date'] == month
    return False


def verify_source_endpoints(session, kind, requested, effective):
    if not official_source_url(session, kind, requested):
        raise ValueError('source request endpoint or query differs from approved TWSE routes')
    if not official_source_url(session, kind, effective):
        raise ValueError('source effective endpoint or query differs from approved TWSE routes')
