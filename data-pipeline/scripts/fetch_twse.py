# -*- coding: utf-8 -*-
"""
證交所每日資料(盤後):
1. STOCK_DAY_ALL  全市場當日收盤(OpenAPI,只回最新一天 → 每天存一份快照累積歷史)
2. T86            三大法人個股買賣超
3. MI_MARGN       全市場融資融券餘額
4. FMTQIK         加權指數日資料(整月)
假日/未開盤時 API 回傳空資料或 stat != OK,一律優雅跳過。
輸出:docs/data/raw/{quotes,t86,margin}_YYYY-MM-DD.json + docs/data/taiex.json
"""
import json
import os

from common import RAW_DIR, get_json, load_json, num, roc_to_iso, save_json, today_tpe


def fetch_quotes():
    """全市場當日收盤快照。回傳交易日(ISO)或 None。"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    data = get_json(url)
    if not data or not isinstance(data, list):
        print("[warn] STOCK_DAY_ALL 無資料")
        return None
    rows = []
    trade_date = None
    for r in data:
        code = str(r.get("Code", "")).strip()
        # 只留 4 碼純數字個股/ETF,排除權證等
        if len(code) != 4 or not code.isdigit():
            continue
        d = str(r.get("Date", "")).strip()  # 格式 1150707(民國) 或 20260707
        if trade_date is None and d:
            if len(d) == 7:
                trade_date = roc_to_iso(f"{d[:3]}/{d[3:5]}/{d[5:]}")
            elif len(d) == 8:
                trade_date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        rows.append({
            "c": code,
            "n": r.get("Name", ""),
            "close": num(r.get("ClosingPrice")),
            "chg": num(r.get("Change")),
            "vol": num(r.get("TradeVolume")),   # 股數
            "high": num(r.get("HighestPrice")),
            "open": num(r.get("OpeningPrice")),
            "low": num(r.get("LowestPrice")),
        })
    if not rows or trade_date is None:
        print("[warn] STOCK_DAY_ALL 解析後為空")
        return None
    path = os.path.join(RAW_DIR, f"quotes_{trade_date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] quotes {trade_date} n={len(rows)}")
    return trade_date


def _rwd(url, params):
    """TWSE RWD API:stat=='OK' 才有資料"""
    j = get_json(url, params=params)
    if not j or j.get("stat") != "OK":
        return None
    return j


def fetch_t86(date_iso):
    """三大法人個股買賣超(單位:股)"""
    ymd = date_iso.replace("-", "")
    j = _rwd("https://www.twse.com.tw/rwd/zh/fund/T86",
             {"date": ymd, "selectType": "ALLBUT0999", "response": "json"})
    if j is None:  # 舊路徑備援
        j = _rwd("https://www.twse.com.tw/fund/T86",
                 {"date": ymd, "selectType": "ALLBUT0999", "response": "json"})
    if j is None:
        print(f"[warn] T86 {date_iso} 無資料(可能未收盤或假日)")
        return
    fields = j.get("fields", [])

    def idx(*keywords):
        for i, f in enumerate(fields):
            if all(k in f for k in keywords):
                return i
        return None

    i_code = idx("證券代號")
    i_f = idx("外陸資買賣超")            # 外陸資買賣超股數(不含外資自營商)
    i_t = idx("投信買賣超")
    i_d1 = idx("自營商買賣超", "自行")    # 自營商買賣超股數(自行買賣)
    i_d2 = idx("自營商買賣超", "避險")    # 自營商買賣超股數(避險)
    i_all = idx("三大法人買賣超")
    if None in (i_code, i_f, i_t, i_all):
        print(f"[error] T86 欄位對不上: {fields}")
        return
    rows = []
    for r in j.get("data", []):
        code = str(r[i_code]).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        dealer = (num(r[i_d1]) or 0) + (num(r[i_d2]) or 0) if i_d1 is not None else None
        rows.append({
            "c": code,
            "f": num(r[i_f]) or 0,
            "t": num(r[i_t]) or 0,
            "d": dealer if dealer is not None else 0,
            "all": num(r[i_all]) or 0,
        })
    path = os.path.join(RAW_DIR, f"t86_{date_iso}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] t86 {date_iso} n={len(rows)}")


def fetch_margin(date_iso):
    """全市場融資融券餘額 → 使用率 = 融資今日餘額/融資限額"""
    ymd = date_iso.replace("-", "")
    j = _rwd("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
             {"date": ymd, "selectType": "ALL", "response": "json"})
    if j is None:
        print(f"[warn] MI_MARGN {date_iso} 無資料")
        return
    # RWD 可能回傳 tables 陣列,找出含「股票代號」欄位的那張表
    tables = j.get("tables") or [j]
    table = None
    for t in tables:
        fs = t.get("fields") or []
        if any("代號" in f for f in fs):
            table = t
            break
    if table is None:
        print(f"[error] MI_MARGN 找不到個股表")
        return
    fields = table["fields"]

    def idx(*keywords):
        for i, f in enumerate(fields):
            if all(k in f for k in keywords):
                return i
        return None

    i_code = idx("代號")
    i_bal = idx("今日餘額")   # 第一組(融資)的今日餘額
    i_lim = idx("限額")
    if None in (i_code, i_bal, i_lim):
        print(f"[error] MI_MARGN 欄位對不上: {fields}")
        return
    rows = []
    for r in table.get("data", []):
        code = str(r[i_code]).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        bal, lim = num(r[i_bal]), num(r[i_lim])
        if bal is None or not lim:
            continue
        rows.append({"c": code, "bal": bal, "lim": lim,
                     "use": round(bal / lim * 100, 2)})
    path = os.path.join(RAW_DIR, f"margin_{date_iso}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] margin {date_iso} n={len(rows)}")


def fetch_taiex():
    """加權指數:FMTQIK 一次回整月,累積進 taiex.json"""
    hist = {r["date"]: r for r in (load_json("taiex.json", default=[]) or [])}
    ymd = today_tpe().strftime("%Y%m01")
    j = _rwd("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK",
             {"date": ymd, "response": "json"})
    if j is None:
        print("[warn] FMTQIK 無資料")
        return
    fields = j.get("fields", [])
    try:
        i_date = next(i for i, f in enumerate(fields) if "日期" in f)
        i_idx = next(i for i, f in enumerate(fields) if "加權" in f)
        i_val = next(i for i, f in enumerate(fields) if "成交金額" in f)
    except StopIteration:
        print(f"[error] FMTQIK 欄位對不上: {fields}")
        return
    for r in j.get("data", []):
        d = roc_to_iso(r[i_date])
        if d:
            hist[d] = {"date": d, "close": num(r[i_idx]),
                       "value": num(r[i_val])}
    rows = sorted(hist.values(), key=lambda x: x["date"])
    save_json(rows, "taiex.json")
    print(f"[ok] taiex days={len(rows)} latest={rows[-1] if rows else None}")


def main():
    trade_date = fetch_quotes()
    fetch_taiex()
    if trade_date:
        fetch_t86(trade_date)
        fetch_margin(trade_date)
    else:
        print("[info] 今日無成交快照(假日?),T86/融資略過")


if __name__ == "__main__":
    main()
