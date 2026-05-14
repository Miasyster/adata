"""akshare provider — free A-share data from East Money (东方财富)."""

from __future__ import annotations

import logging

import pandas as pd

from ..schema import DAILY_COLUMNS, CodeNormalizer
from . import register
from .base import BaseProvider

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    _HAS_AK = True
except ImportError:
    _HAS_AK = False
    ak = None  # type: ignore[assignment]


def _ensure_installed():
    if not _HAS_AK:
        raise RuntimeError("akshare is not installed. Run: pip install akshare")


_CN_COLUMNS = {
    "日期": "trade_date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "pct_change",
}


_ADJUST_MAP = {"qfq": "qfq", "hfq": "hfq", "none": ""}


def _fetch_one_stock(symbol: str, bs_code: str, start_date: str, end_date: str, adjust: str = "qfq") -> pd.DataFrame | None:
    ak_start = start_date.replace("-", "")
    ak_end = end_date.replace("-", "")

    df = ak.stock_zh_a_hist(
        symbol=symbol, period="daily",
        start_date=ak_start, end_date=ak_end, adjust=adjust,
    )
    if df is None or len(df) == 0:
        return None

    df = df.rename(columns=_CN_COLUMNS)
    df["stock_code"] = bs_code
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for col in ("open", "high", "low", "close", "volume", "amount", "pct_change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[DAILY_COLUMNS].sort_values("trade_date")


def _fetch_one_etf(symbol: str, bs_code: str, start_date: str, end_date: str, adjust: str = "qfq") -> pd.DataFrame | None:
    ak_start = start_date.replace("-", "")
    ak_end = end_date.replace("-", "")

    df = ak.fund_etf_hist_em(
        symbol=symbol, period="daily",
        start_date=ak_start, end_date=ak_end, adjust=adjust,
    )
    if df is None or len(df) == 0:
        return None

    df = df.rename(columns=_CN_COLUMNS)
    df["stock_code"] = bs_code
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for col in ("open", "high", "low", "close", "volume", "amount", "pct_change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[DAILY_COLUMNS].sort_values("trade_date")


@register
class AkshareProvider(BaseProvider):
    name = "akshare"
    supported_asset_types = {"stock", "etf"}

    _ETF_PREFIXES = ("51", "52", "56", "58", "59", "15", "16")

    def fetch_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        _ensure_installed()
        all_dfs: list[pd.DataFrame] = []
        ak_adjust = _ADJUST_MAP.get(adjust, "qfq")

        for i, raw_code in enumerate(codes):
            bs_code = CodeNormalizer.normalize(raw_code)
            symbol = bs_code.split(".")[1] if "." in bs_code else raw_code

            try:
                if symbol.startswith(self._ETF_PREFIXES):
                    df = _fetch_one_etf(symbol, bs_code, start_date, end_date, ak_adjust)
                else:
                    df = _fetch_one_stock(symbol, bs_code, start_date, end_date, ak_adjust)

                if df is not None and len(df) > 0:
                    all_dfs.append(df)
            except Exception as e:
                logger.warning("akshare fetch failed for %s: %s", raw_code, e)

            if (i + 1) % 20 == 0:
                logger.info("akshare progress: %d/%d", i + 1, len(codes))

        if not all_dfs:
            return pd.DataFrame(columns=DAILY_COLUMNS)
        return pd.concat(all_dfs, ignore_index=True)

    def fetch_benchmark(
        self,
        name: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        _ensure_installed()

        index_map = {
            "hs300": "000300",
            "zz500": "000905",
            "csi500": "000905",
            "csi1000": "000852",
            "sz50": "000016",
        }
        symbol = index_map.get(name)
        if not symbol:
            raise ValueError(f"Unknown benchmark '{name}' for akshare")

        ak_start = start_date.replace("-", "")
        ak_end = end_date.replace("-", "")

        df = ak.stock_zh_index_daily_em(symbol=symbol, start_date=ak_start, end_date=ak_end)
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=["trade_date", "close", "daily_return"])

        if "date" in df.columns:
            df = df.rename(columns={"date": "trade_date"})
        elif "日期" in df.columns:
            df = df.rename(columns={"日期": "trade_date"})

        if "收盘" in df.columns:
            df = df.rename(columns={"收盘": "close"})

        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.sort_values("trade_date")
        df["daily_return"] = df["close"].pct_change()
        return df[["trade_date", "close", "daily_return"]].copy()

    def list_instruments(
        self,
        asset_type: str,
        date: str | None = None,
    ) -> list[str]:
        _ensure_installed()

        if asset_type == "stock":
            df = ak.stock_zh_a_spot_em()
            if df is None or len(df) == 0:
                return []
            codes = []
            for raw in df["代码"]:
                raw = str(raw)
                if raw.startswith("6"):
                    codes.append(f"sh.{raw}")
                elif raw.startswith(("0", "3")):
                    codes.append(f"sz.{raw}")
            return sorted(codes)

        if asset_type == "etf":
            df = ak.fund_etf_spot_em()
            if df is None or len(df) == 0:
                return []
            codes = []
            for raw in df["代码"]:
                raw = str(raw)
                if raw.startswith(("5", "6")):
                    codes.append(f"sh.{raw}")
                elif raw.startswith(("1", "0")):
                    codes.append(f"sz.{raw}")
            return sorted(codes)

        raise ValueError(f"akshare list_instruments: unsupported asset_type '{asset_type}'")

    def list_universe(
        self,
        universe: str,
        date: str | None = None,
    ) -> list[str]:
        raise NotImplementedError(
            "akshare does not support universe queries. Use rqdatac or baostock."
        )
