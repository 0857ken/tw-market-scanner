"""Exact current CSV linked by government dataset 11549. No arbitrary URL/date."""
import csv
import hashlib
import io
from urllib.request import Request, urlopen

URL='https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data'
FIELDS={'日期':'Date','證券代號':'Code','證券名稱':'Name','收盤價':'ClosingPrice','成交股數':'TradeVolume','漲跌價差':'Change'}


def parse_twse_csv(body):
    reader=csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    if not set(FIELDS)<=set(reader.fieldnames or []):raise ValueError('Unexpected official CSV header')
    rows=[{target:r.get(source) for source,target in FIELDS.items()} for r in reader]
    if not rows:raise ValueError('Empty official CSV')
    return rows


def fetch_twse_csv(_url=None, params=None):
    if params:raise ValueError('Historical/date parameters are prohibited')
    request=Request(URL,headers={'User-Agent':'TW-Market-Scanner/3.0 (current open dataset 11549)','Accept':'text/csv'})
    with urlopen(request,timeout=15) as response:
        if response.url != URL:raise ValueError('Unexpected CSV redirect')
        body=response.read(4_000_001)
    if len(body)>4_000_000:raise ValueError('CSV exceeds 4 MB limit')
    return parse_twse_csv(body),hashlib.sha256(body).hexdigest(),URL
