"""Canonical dates and unambiguous JSON for evidence, with no trust claim."""
from datetime import date
import json
import re
from urllib.parse import urlencode


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
