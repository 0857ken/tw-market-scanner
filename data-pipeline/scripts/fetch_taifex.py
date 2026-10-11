# -*- coding: utf-8 -*-
"""
期交所三大法人-臺股期貨淨未平倉口數
主要來源:期交所 OpenAPI(只回最新一日)
備援來源:官方 CSV 下載端點 futContractsDateDown(可指定日期,Big5 編碼)
輸出:docs/data/futures.json(逐日累積)
"""
import csv
import io

import requests

from common import HEADERS, get_json, load_json, num, save_json, today_tpe

OPENAPI = ("https://openapi.taifex.com.tw/v1/"
           "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate")
FALLBACK = "https://www.taifex.com.tw/cht/3/futContractsDateDown"

IDENTITY = {"外資": "foreign", "外資及陸資": "foreign",
            "投信": "trust", "自營商": "dealer"}


def _norm_date(s):
    s = str(s).strip().replace("/", "-")
    p = s.split("-")
    return f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}" if len(p) == 3 else None


def _pick(rec, *keywords):
    """在 dict 裡找 key 同時包含所有關鍵字的值(容錯欄位命名差異)"""
    for k, v in rec.items():
        if all(kw in k for kw in keywords):
            return v
    return None


def from_openapi():
    data = get_json(OPENAPI)
    if not data or not isinstance(data, list):
        return None
    out = {}
    date = None
    for rec in data:
        name = str(_pick(rec, "商品") or _pick(rec, "Contract") or "")
        # 只取臺股期貨(大台),排除小型/微型
        if "臺股期貨" not in name or "小型" in name or "微型" in name:
            continue
        ident = str(_pick(rec, "身") or _pick(rec, "Trader") or "").strip()
        key = next((v for k, v in IDENTITY.items() if k in ident), None)
        if key is None:
            continue
        net = _pick(rec, "多空", "未平倉", "口數") or _pick(rec, "未平倉", "淨額")
        d = _pick(rec, "日期") or _pick(rec, "Date")
        if net is None or d is None:
            continue
        date = _norm_date(d)
        out[key] = int(num(net) or 0)
    if date and out:
        return date, out
    return None


def from_fallback(date_iso):
    """POST 官方下載端點取得指定日期 CSV(cp950)"""
    d = date_iso.replace("-", "/")
    try:
        r = requests.post(FALLBACK, headers=HEADERS, timeout=30, data={
            "down_type": "1", "queryStartDate": d, "queryEndDate": d,
            "commodity_id": "TXF",
        })
        r.encoding = "cp950"
        rows = list(csv.reader(io.StringIO(r.text)))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] fallback 失敗 {e}")
        return None
    if len(rows) < 2:
        return None
    header = rows[0]

    def col(*keywords):
        for i, h in enumerate(header):
            if all(k in h for k in keywords):
                return i
        return None

    i_id = col("身")
    i_net = col("多空", "未平倉", "口數")
    if i_net is None:
        i_net = col("未平倉", "淨額", "口數")
    if i_id is None or i_net is None:
        print(f"[warn] fallback 欄位對不上: {header}")
        return None
    out = {}
    for r_ in rows[1:]:
        if len(r_) <= max(i_id, i_net):
            continue
        ident = r_[i_id].strip()
        key = next((v for k, v in IDENTITY.items() if k in ident), None)
        if key:
            out[key] = int(num(r_[i_net]) or 0)
    return (date_iso, out) if out else None


def main():
    hist = {r["date"]: r for r in (load_json("futures.json", default=[]) or [])}
    got = from_openapi()
    if got is None:
        print("[info] OpenAPI 無資料,改用備援下載端點")
        got = from_fallback(today_tpe().strftime("%Y-%m-%d"))
    if got is None:
        print("[warn] 期交所今日無資料(假日?),沿用舊檔")
        return
    date, pos = got
    rec = {"date": date,
           "foreign": pos.get("foreign", 0),
           "trust": pos.get("trust", 0),
           "dealer": pos.get("dealer", 0)}
    rec["total"] = rec["foreign"] + rec["trust"] + rec["dealer"]
    hist[date] = rec
    rows = sorted(hist.values(), key=lambda x: x["date"])
    save_json(rows, "futures.json")
    print(f"[ok] futures {rec}")


if __name__ == "__main__":
    main()
