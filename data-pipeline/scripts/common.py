# -*- coding: utf-8 -*-
"""共用工具:HTTP 請求、路徑、日期處理"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "docs", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)

TPE = timezone(timedelta(hours=8))  # 台北時區

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}


def today_tpe():
    return datetime.now(TPE).date()


def get_json(url, params=None, retries=3, sleep=3):
    """帶重試的 GET,回傳 JSON;失敗回傳 None(不讓整個 pipeline 掛掉)"""
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"[warn] {url} HTTP {r.status_code} (try {i+1}/{retries})")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {url} {e} (try {i+1}/{retries})")
        time.sleep(sleep)
    return None


def save_json(obj, *path_parts):
    path = os.path.join(DATA_DIR, *path_parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[ok] wrote {path}")


def load_json(*path_parts, default=None):
    path = os.path.join(DATA_DIR, *path_parts)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def num(s):
    """'1,234' / '--' / '' → float 或 None"""
    if s is None:
        return None
    s = str(s).replace(",", "").replace("+", "").strip()
    if s in ("", "--", "-", "N/A", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def roc_to_iso(s):
    """民國日期 '115/07/07' → '2026-07-07';已是西元則原樣轉換"""
    s = str(s).strip().replace("-", "/")
    parts = s.split("/")
    if len(parts) != 3:
        return None
    y, m, d = parts
    y = int(y)
    if y < 1911:
        y += 1911
    return f"{y:04d}-{int(m):02d}-{int(d):02d}"
