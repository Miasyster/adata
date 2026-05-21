"""Configuration — data directory and defaults."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DEFAULT_START = "2015-01-01"
DEFAULT_BATCH_SIZE = 200

BENCHMARK_MAP = {
    "hs300": {"baostock": "sh.000300", "rqdatac": "000300.XSHG", "name": "沪深300"},
    "zz500": {"baostock": "sh.000905", "rqdatac": "000905.XSHG", "name": "中证500"},
    "csi500": {"baostock": "sh.000905", "rqdatac": "000905.XSHG", "name": "中证500"},
    "csi1000": {"baostock": "sh.000852", "rqdatac": "000852.XSHG", "name": "中证1000"},
    "sz50": {"baostock": "sh.000016", "rqdatac": "000016.XSHG", "name": "上证50"},
    "csi2000": {"baostock": "sz.399303", "rqdatac": "399303.XSHE", "name": "中证2000"},
    "gem": {"baostock": "sz.399006", "rqdatac": "399006.XSHE", "name": "创业板指"},
    "hsi": {"rqdatac": "HSI.XHKG", "name": "恒生指数"},
    "hscei": {"rqdatac": "HSCEI.XHKG", "name": "恒生中国企业指数"},
    "hstech": {"rqdatac": "HSTECH.XHKG", "name": "恒生科技指数"},
}

UNIVERSE_INDEX_MAP = {
    "hs300": "000300.XSHG",
    "csi500": "000905.XSHG",
    "zz500": "000905.XSHG",
    "csi1000": "000852.XSHG",
    "hsi": "HSI.XHKG",
    "hstech": "HSTECH.XHKG",
}


def get_data_dir() -> Path:
    d = Path(os.environ.get("ADATA_DIR", "") or str(Path.home() / ".adata"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def approx_trading_days(start_date: str, end_date: str) -> int:
    """Approximate A-share/HK trading day count between two dates (inclusive).

    Uses business days minus ~4.3% for holidays. Works for both markets.
    """
    import numpy as np

    s = pd.Timestamp(start_date).date()
    e = pd.Timestamp(end_date).date()
    if s > e:
        return 0
    weekdays = int(np.busday_count(s, e)) + 1
    return max(1, int(weekdays * 0.957))
