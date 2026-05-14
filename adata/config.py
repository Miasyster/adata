"""Configuration — data directory and defaults."""

from __future__ import annotations

import os
from pathlib import Path

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
}

UNIVERSE_INDEX_MAP = {
    "hs300": "000300.XSHG",
    "csi500": "000905.XSHG",
    "zz500": "000905.XSHG",
    "csi1000": "000852.XSHG",
    "csi2000": None,
}


def get_data_dir() -> Path:
    d = Path(os.environ.get("ADATA_DIR", "") or str(Path.home() / ".adata"))
    d.mkdir(parents=True, exist_ok=True)
    return d
