"""Build the fixed November 2026 rebound snapshot from the reviewed CSVs."""
import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/rebound-public'
OUTPUT = ROOT / 'frontend/rebound-map/public-snapshot.json'
DATES = tuple(f'2026-11-{day:02d}' for day in (2, 3, 4, 5, 6, 9, 10, 11))
LICENSE = {'name': '政府資料開放授權條款－第1版', 'url': 'https://data.gov.tw/license'}
SOURCES = (
    ('11755', '發行量加權股價指數歷史資料',
     'https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=open_data',
     '1bbd678558c60825061d044dbe3140d473005f1865451c3d0eb397bc25e0b5c2'),
    ('11672', '盤後資訊 > 每日市場成交資訊',
     'https://www.twse.com.tw/exchangeReport/FMTQIK?response=open_data',
     '0b9856a349aeb12b9627dd3ecd84bfdb57eb9de1dd755c05c5085b638800eef5'),
)
SIGNAL_LABELS = {
    'seasonal_touch': '盤中觸及季線且季線高於半年線',
    'margin_drop_2': '融資單日下降 ≥2%',
    'margin_drop5_5': '融資五日下降 ≥5%',
    'drawdown10': '距20日高點下降 ≥10%',
    'drawdown7': '距20日高點下降 ≥7%',
    'kd_k20': '隨機指標 K ≤20（9,3,3）',
    'day_drop3': '當日收盤跌幅 ≥3%',
    'high_turnover_fall': '下跌且成交額 > 前20日均額 1.4倍',
    'lower_wick': '收盤弱勢且下影長度 ≥前收 1.2%',
    'down4': '連續收盤下跌 ≥4 日',
    'foreign_sell5': '外資連賣 ≥5日',
    'foreign_sell8': '外資連賣 ≥8日',
    'foreign_large_sell': '外資單日賣超 >1500億元',
    'foreign_turn_buy': '外資連賣至少2日後首日轉買（自訂）',
    'futures_short_high': '外資台指期淨空單創前60日新高',
}


def read_source(dataset_id, digest, columns):
    raw = (FIXTURES / f'{dataset_id}.csv').read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f'{dataset_id} source SHA256 mismatch')
    table = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if table.fieldnames != columns:
        raise ValueError(f'{dataset_id} unexpected CSV columns')
    rows = {}
    for row in table:
        roc = row['日期']
        if len(roc) != 7 or not roc.isdecimal():
            raise ValueError('Invalid ROC date')
        day = date(1911 + int(roc[:3]), int(roc[3:5]), int(roc[5:])).isoformat()
        if day in rows:
            raise ValueError('Duplicate trade date')
        rows[day] = row
    if tuple(rows) != DATES:
        raise ValueError('Unexpected trade date range')
    return rows


def public_signals(rows, i):
    # Preserve the R3.6 price predicates. Four consecutive declines require five
    # closes, even on a date where the observed partial streak is already broken.
    states = dict.fromkeys(SIGNAL_LABELS)
    if i > 0:
        row, prev = rows[i], rows[i-1]
        states['day_drop3'] = row['close']/prev['close']-1 <= -.03
        states['lower_wick'] = (
            (min(row['open'], row['close'])-row['low'])/prev['close'] >= .012
            and row['close'] < prev['close']
        )
    if i >= 4:
        states['down4'] = all(rows[j]['close'] < rows[j-1]['close'] for j in range(i-3, i+1))
    return states


def build():
    ohlc_fields = ('開盤指數', '最高指數', '最低指數', '收盤指數')
    prices = read_source('11755', SOURCES[0][3], ['日期', *ohlc_fields])
    turnover = read_source('11672', SOURCES[1][3], ['日期', '成交股數', '成交金額', '成交筆數', '發行量加權股價指數', '漲跌點數'])
    rows, checks = [], []
    for day in DATES:
        o, h, l, c = (Decimal(prices[day][field]) for field in ohlc_fields)
        other_close = Decimal(turnover[day]['發行量加權股價指數'])
        amount = int(turnover[day]['成交金額'])
        if not 0 < l <= min(o, c) <= max(o, c) <= h or c != other_close or amount <= 0:
            raise ValueError(f'OHLC or turnover mismatch on {day}')
        rows.append(dict(date=day, open=float(o), high=float(h), low=float(l), close=float(c), turnover=amount))
        checks.append(dict(date=day, ohlc_close=str(c), turnover_close=str(other_close), match=True))
    return {
        'price_as_of': DATES[-1],
        'rows': rows,
        'signals': [public_signals(rows, i) for i in range(len(rows))],
        'signal_labels': SIGNAL_LABELS,
        'sources': [
            dict(id=dataset_id, name=name, agency='金融監督管理委員會證券期貨局',
                 origin='臺灣證券交易所', dataset_url=f'https://data.gov.tw/dataset/{dataset_id}',
                 raw_url=url, raw_sha256=digest, first_date=DATES[0], last_date=DATES[-1], license=LICENSE)
            for dataset_id, name, url, digest in SOURCES
        ],
        'checks': checks,
    }


if __name__ == '__main__':
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
