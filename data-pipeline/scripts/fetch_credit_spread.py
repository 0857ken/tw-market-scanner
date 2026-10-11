# -*- coding: utf-8 -*-
"""
信用利差紅綠燈資料
指標 = 1 - rolling_percentile_rank(HYG/SHY, 189天)
重點:必須使用「還原權息價」(auto_adjust=True),否則 HYG 高配息會讓比率失真。
輸出:docs/data/credit_spread.json
"""
import sys

import yfinance as yf

from common import save_json

WINDOW = 189
THRESHOLD = 0.30
BUFFER = 0.05


def main():
    # auto_adjust=True → Close 即為還原權息價(Adj Close)
    df = yf.download(
        ["HYG", "SHY", "SPY"],
        period="6y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )["Close"].dropna()

    if df.empty or len(df) < WINDOW + 10:
        print("[error] yfinance 回傳資料不足,略過本次更新")
        sys.exit(0)  # 不讓 workflow 失敗,沿用舊檔

    ratio = df["HYG"] / df["SHY"]

    # 1 - rolling percentile rank(含當日,與網頁邏輯一致)
    def pct_rank(window):
        return (window <= window.iloc[-1]).sum() / len(window)

    indicator = 1.0 - ratio.rolling(WINDOW).apply(pct_rank, raw=False)

    out = []
    pos = 0
    prev_ind = None
    for dt, ind in indicator.dropna().items():
        # 訊號延遲 1 天:今天的持倉由「昨天」的指標決定
        if prev_ind is not None:
            pos = 1 if prev_ind < THRESHOLD else 0
        prev_ind = ind
        out.append({
            "date": dt.strftime("%Y-%m-%d"),
            "ratio": round(float(ratio.loc[dt]), 4),
            "spy": round(float(df["SPY"].loc[dt]), 2),
            "indicator": round(float(ind), 4),
            "position": pos,
        })

    save_json(
        {
            "meta": {
                "window": WINDOW,
                "threshold": THRESHOLD,
                "buffer": BUFFER,
                "source": "Yahoo Finance (adjusted close)",
                "updated": out[-1]["date"],
            },
            "rows": out,
        },
        "credit_spread.json",
    )
    print(f"[ok] credit spread rows={len(out)} latest={out[-1]}")


if __name__ == "__main__":
    main()
