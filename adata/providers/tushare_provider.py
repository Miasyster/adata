"""tushare provider — Tushare Pro financial data."""

from __future__ import annotations

import logging
import os

import pandas as pd

from ..schema import DAILY_COLUMNS, CodeNormalizer
from . import register
from .base import BaseProvider

logger = logging.getLogger(__name__)

try:
    import tushare as ts

    _HAS_TS = True
except ImportError:
    _HAS_TS = False
    ts = None  # type: ignore[assignment]

_pro = None

_BENCHMARK_CODES = {
    "hs300": "000300.SH",
    "zz500": "000905.SH",
    "csi500": "000905.SH",
    "csi1000": "000852.SH",
    "sz50": "000016.SH",
    "csi2000": "932000.CSI",
}

_UNIVERSE_CODES = {
    "hs300": "000300.SH",
    "zz500": "000905.SH",
    "csi500": "000905.SH",
    "csi1000": "000852.SH",
}


def _ensure_installed():
    if not _HAS_TS:
        raise RuntimeError("tushare is not installed. Run: pip install tushare")


def _get_pro():
    global _pro
    if _pro is not None:
        return _pro
    _ensure_installed()
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN must be set in environment")
    _pro = ts.pro_api(token)
    logger.info("tushare pro initialized")
    return _pro


def _to_ts_code(code: str) -> str:
    """sh.600519 → 600519.SH"""
    code = CodeNormalizer.normalize(code)
    parts = code.split(".", 1)
    if len(parts) == 2 and parts[0] in ("sh", "sz"):
        return f"{parts[1]}.{parts[0].upper()}"
    return code


def _from_ts_code(ts_code: str) -> str:
    """600519.SH → sh.600519"""
    parts = ts_code.split(".", 1)
    if len(parts) == 2 and parts[1] in ("SH", "SZ"):
        return f"{parts[1].lower()}.{parts[0]}"
    return ts_code


def _to_ts_date(date_str: str) -> str:
    """2025-01-02 → 20250102"""
    return date_str.replace("-", "")


@register
class TushareProvider(BaseProvider):
    name = "tushare"
    supported_asset_types = {"stock", "index"}

    def fetch_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        pro = _get_pro()
        ts_start = _to_ts_date(start_date)
        ts_end = _to_ts_date(end_date)
        all_dfs: list[pd.DataFrame] = []

        for i, raw_code in enumerate(codes):
            ts_code = _to_ts_code(raw_code)
            bs_code = CodeNormalizer.normalize(raw_code)
            try:
                df = pro.daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
                if df is not None and len(df) > 0:
                    out = pd.DataFrame()
                    out["trade_date"] = pd.to_datetime(df["trade_date"])
                    out["stock_code"] = bs_code
                    out["open"] = pd.to_numeric(df["open"], errors="coerce")
                    out["high"] = pd.to_numeric(df["high"], errors="coerce")
                    out["low"] = pd.to_numeric(df["low"], errors="coerce")
                    out["close"] = pd.to_numeric(df["close"], errors="coerce")
                    out["volume"] = pd.to_numeric(df["vol"], errors="coerce") * 100.0
                    out["amount"] = pd.to_numeric(df["amount"], errors="coerce") * 1000.0
                    out["pct_change"] = pd.to_numeric(df["pct_chg"], errors="coerce")
                    all_dfs.append(out[DAILY_COLUMNS].sort_values("trade_date"))
            except Exception as e:
                logger.warning("tushare fetch failed for %s: %s", raw_code, e)

            if (i + 1) % 50 == 0:
                logger.info("tushare progress: %d/%d", i + 1, len(codes))

        if not all_dfs:
            return pd.DataFrame(columns=DAILY_COLUMNS)
        return pd.concat(all_dfs, ignore_index=True)

    def fetch_benchmark(
        self,
        name: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        pro = _get_pro()
        ts_code = _BENCHMARK_CODES.get(name)
        if not ts_code:
            raise ValueError(f"Unknown benchmark '{name}' for tushare. Available: {list(_BENCHMARK_CODES)}")

        ts_start = _to_ts_date(start_date)
        ts_end = _to_ts_date(end_date)

        df = pro.index_daily(
            ts_code=ts_code,
            start_date=ts_start,
            end_date=ts_end,
        )
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=["trade_date", "close", "daily_return"])

        out = pd.DataFrame()
        out["trade_date"] = pd.to_datetime(df["trade_date"])
        out["close"] = pd.to_numeric(df["close"], errors="coerce")
        out = out.sort_values("trade_date")
        out["daily_return"] = out["close"].pct_change()
        return out[["trade_date", "close", "daily_return"]].copy()

    def list_instruments(
        self,
        asset_type: str,
        date: str | None = None,
    ) -> list[str]:
        pro = _get_pro()
        if asset_type != "stock":
            raise ValueError(f"tushare list_instruments only supports 'stock', got '{asset_type}'")

        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code",
        )
        if df is None or len(df) == 0:
            return []

        codes = []
        for ts_code in df["ts_code"]:
            codes.append(_from_ts_code(ts_code))
        return sorted(codes)

    def list_universe(
        self,
        universe: str,
        date: str | None = None,
    ) -> list[str]:
        pro = _get_pro()
        index_code = _UNIVERSE_CODES.get(universe)
        if not index_code:
            raise ValueError(f"Unknown universe '{universe}' for tushare. Available: {list(_UNIVERSE_CODES)}")

        from datetime import datetime
        ts_date = _to_ts_date(date) if date else datetime.now().strftime("%Y%m%d")

        df = pro.index_weight(
            index_code=index_code,
            start_date=ts_date,
            end_date=ts_date,
        )
        if df is None or len(df) == 0:
            df = pro.index_weight(index_code=index_code)
            if df is None or len(df) == 0:
                return []
            latest_date = df["trade_date"].max()
            df = df[df["trade_date"] == latest_date]

        codes = []
        for ts_code in df["con_code"]:
            codes.append(_from_ts_code(ts_code))
        return sorted(codes)
