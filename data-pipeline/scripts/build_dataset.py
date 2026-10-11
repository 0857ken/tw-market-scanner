# -*- coding: utf-8 -*-
"""
把累積的 raw 快照組合成前端要吃的 market.json
計算:漲跌幅、MA、市場廣度、N日突破、法人連續買賣超、融資使用率
注意:MA/廣度/突破需要累積足夠天數的快照才有意義(程式會自動標註可用度)
"""
import json
import os
import re
from collections import defaultdict

from common import DATA_DIR, RAW_DIR, load_json, save_json

KEEP_DAYS = 260          # 保留約一年
BREAKOUT_NS = [20, 60, 120, 240]
STREAK_MIN = 3


def _dates_of(prefix):
    pat = re.compile(rf"{prefix}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    out = []
    for fn in os.listdir(RAW_DIR):
        m = pat.match(fn)
        if m:
            out.append(m.group(1))
    return sorted(out)[-KEEP_DAYS:]


def _load_raw(prefix, date):
    with open(os.path.join(RAW_DIR, f"{prefix}_{date}.json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    qdates = _dates_of("quotes")
    if not qdates:
        print("[warn] 尚無任何 quotes 快照,無法建置(先跑 fetch_twse.py)")
        return

    # ---- 價格序列 ----
    closes = defaultdict(dict)   # code -> {date: close}
    vols = defaultdict(dict)
    names, last_chg = {}, {}
    for d in qdates:
        for r in _load_raw("quotes", d):
            if r["close"] is None:
                continue
            closes[r["c"]][d] = r["close"]
            vols[r["c"]][d] = r["vol"] or 0
            names[r["c"]] = r["n"]
            last_chg[r["c"]] = r
    last_date = qdates[-1]

    # ---- 法人序列 ----
    tdates = _dates_of("t86")
    inst = defaultdict(lambda: defaultdict(dict))  # kind -> code -> {date: net股}
    for d in tdates:
        for r in _load_raw("t86", d):
            inst["f"][r["c"]][d] = r["f"]
            inst["t"][r["c"]][d] = r["t"]
            inst["d"][r["c"]][d] = r["d"]

    def streak(code, kind):
        seq = [inst[kind][code].get(d) for d in tdates]
        seq = [v for v in seq if v is not None]
        if not seq:
            return {"dir": 0, "days": 0, "sum": 0}
        sgn = 1 if seq[-1] > 0 else -1 if seq[-1] < 0 else 0
        days = tot = 0
        for v in reversed(seq):
            if sgn and ((v > 0) == (sgn > 0)) and v != 0:
                days += 1
                tot += v
            else:
                break
        return {"dir": sgn, "days": days, "sum": round(tot / 1000)}  # 股→張

    # ---- 融資 ----
    mdates = _dates_of("margin")
    margin = {r["c"]: r for r in _load_raw("margin", mdates[-1])} if mdates else {}

    # ---- 個股彙整 ----
    stocks = []
    for code, series in closes.items():
        ds = sorted(series)
        px = [series[d] for d in ds]
        if len(px) < 2:
            continue
        r0 = last_chg.get(code, {})
        chg_pct = (r0.get("chg") or 0) / px[-2] * 100 if px[-2] else 0

        def ma(n):
            return round(sum(px[-n:]) / n, 2) if len(px) >= n else None

        breakouts = {}
        for n in BREAKOUT_NS:
            if len(px) >= n + 1:
                prior = max(px[-n - 1:-1])
                breakouts[str(n)] = {
                    "hit": px[-1] > prior,
                    "dist": round((px[-1] / prior - 1) * 100, 2),
                }
        vl = [vols[code].get(d, 0) for d in ds]
        vol_ratio = (round(vl[-1] / (sum(vl[-21:-1]) / 20), 2)
                     if len(vl) >= 21 and sum(vl[-21:-1]) else None)
        mg = margin.get(code)
        stocks.append({
            "sym": code, "name": names.get(code, ""),
            "close": px[-1], "chg": round(chg_pct, 2),
            "vol": round(vl[-1] / 1000),                 # 股→張
            "ma20": ma(20), "ma60": ma(60), "ma120": ma(120),
            "breakouts": breakouts, "volRatio": vol_ratio,
            "inst": {
                "f": round((inst["f"][code].get(last_date, 0)) / 1000),
                "t": round((inst["t"][code].get(last_date, 0)) / 1000),
                "d": round((inst["d"][code].get(last_date, 0)) / 1000),
            } if tdates else None,
            "streaks": {"foreign": streak(code, "f"),
                        "trust": streak(code, "t")} if tdates else None,
            "margin": ({"bal": mg["bal"], "use": mg["use"]} if mg else None),
        })

    # ---- 市場廣度(逐日回算,只算資料足夠的日子) ----
    taiex = load_json("taiex.json", default=[]) or []
    taiex_map = {r["date"]: r["close"] for r in taiex}
    breadth = []
    for i, d in enumerate(qdates):
        n20 = a20 = n60 = a60 = n120 = a120 = up = down = 0
        for code, series in closes.items():
            hist = [series[x] for x in qdates[:i + 1] if x in series]
            if len(hist) < 2:
                continue
            p = hist[-1]
            if hist[-1] > hist[-2]:
                up += 1
            elif hist[-1] < hist[-2]:
                down += 1
            if len(hist) >= 20:
                n20 += 1
                a20 += p > sum(hist[-20:]) / 20
            if len(hist) >= 60:
                n60 += 1
                a60 += p > sum(hist[-60:]) / 60
            if len(hist) >= 120:
                n120 += 1
                a120 += p > sum(hist[-120:]) / 120
        breadth.append({
            "date": d,
            "a20": round(a20 / n20 * 100, 1) if n20 else None,
            "a60": round(a60 / n60 * 100, 1) if n60 else None,
            "a120": round(a120 / n120 * 100, 1) if n120 else None,
            "up": up, "down": down,
            "taiex": taiex_map.get(d),
        })

    # ---- 法人每日合計(億元近似:股數*收盤價;此處輸出張數合計,前端自行呈現) ----
    inst_daily = []
    for d in tdates:
        rec = {"date": d}
        for k in ("f", "t", "d"):
            rec[k] = round(sum(v.get(d, 0) for v in inst[k].values()) / 1000)
        rec["all"] = rec["f"] + rec["t"] + rec["d"]
        inst_daily.append(rec)

    save_json({
        "meta": {
            "updated": last_date,
            "quoteDays": len(qdates),
            "t86Days": len(tdates),
            "note": ("MA20/廣度20 需累積20個交易日;MA60需60日;MA120需120日。"
                     "quoteDays 未達門檻前,對應欄位為 null。"),
        },
        "stocks": stocks,
        "breadth": breadth[-120:],
        "instDaily": inst_daily[-30:],
        "futures": (load_json("futures.json", default=[]) or [])[-30:],
        "taiex": taiex[-260:],
    }, "market.json")
    size = os.path.getsize(os.path.join(DATA_DIR, "market.json")) / 1024
    print(f"[ok] market.json stocks={len(stocks)} days={len(qdates)} size={size:.0f}KB")


if __name__ == "__main__":
    main()
