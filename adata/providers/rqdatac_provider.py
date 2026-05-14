"""rqdatac provider — RiceQuant data service."""

from __future__ import annotations

import logging
import os
import threading

import numpy as np
import pandas as pd

from ..config import BENCHMARK_MAP, UNIVERSE_INDEX_MAP
from ..schema import DAILY_COLUMNS, CodeNormalizer
from . import register
from .base import BaseProvider

logger = logging.getLogger(__name__)

_rq_lock = threading.Lock()
_rq_initialized = False

try:
    import rqdatac

    _HAS_RQDATAC = True
except ImportError:
    _HAS_RQDATAC = False
    rqdatac = None  # type: ignore[assignment]


def _ensure_init():
    global _rq_initialized
    if not _HAS_RQDATAC:
        raise RuntimeError("rqdatac is not installed. Run: pip install rqdatac")
    if _rq_initialized:
        return
    user = os.environ.get("RQDATAC_USERNAME", "")
    pwd = os.environ.get("RQDATAC_PASSWORD", "")
    if not user or not pwd:
        raise RuntimeError(
            "RQDATAC_USERNAME and RQDATAC_PASSWORD must be set in environment"
        )
    with _rq_lock:
        if _rq_initialized:
            return
        rqdatac.init(user, pwd)
        _rq_initialized = True
        logger.info("rqdatac initialized")


def _transform_batch(rq_df: pd.DataFrame) -> pd.DataFrame:
    """Transform rqdatac get_price MultiIndex output → standard schema."""
    df = rq_df.reset_index()

    if "order_book_id" not in df.columns:
        raise ValueError("Expected MultiIndex with order_book_id from rqdatac")

    if "date" in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["stock_code"] = df["order_book_id"].map(CodeNormalizer.from_rqdatac)

    if "total_turnover" in df.columns:
        df["amount"] = df["total_turnover"]
    elif "amount" not in df.columns:
        df["amount"] = 0.0

    if "prev_close" in df.columns:
        df["pct_change"] = ((df["close"] / df["prev_close"]) - 1) * 100
        df.loc[df["prev_close"].isna() | (df["prev_close"] == 0), "pct_change"] = (
            np.nan
        )
    else:
        df = df.sort_values(["stock_code", "trade_date"])
        df["pct_change"] = df.groupby("stock_code")["close"].pct_change() * 100

    for col in ("open", "high", "low", "close", "volume", "amount", "pct_change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[DAILY_COLUMNS].copy().sort_values(["stock_code", "trade_date"])


@register
class RqdatacProvider(BaseProvider):
    name = "rqdatac"
    supported_asset_types = {"stock", "etf", "index"}

    def fetch_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        _ensure_init()
        rq_codes = [CodeNormalizer.to_rqdatac(c) for c in codes]

        rq_df = rqdatac.get_price(
            rq_codes,
            start_date=start_date,
            end_date=end_date,
            frequency="1d",
            adjust_type="pre",
            expect_df=True,
        )
        if rq_df is None or len(rq_df) == 0:
            return pd.DataFrame(columns=DAILY_COLUMNS)

        return _transform_batch(rq_df)

    def fetch_benchmark(
        self,
        name: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        _ensure_init()
        info = BENCHMARK_MAP.get(name)
        if not info:
            raise ValueError(
                f"Unknown benchmark '{name}'. Available: {list(BENCHMARK_MAP)}"
            )

        rq_code = info["rqdatac"]
        rq_df = rqdatac.get_price(
            rq_code,
            start_date=start_date,
            end_date=end_date,
            frequency="1d",
            adjust_type="pre",
            expect_df=True,
        )
        if rq_df is None or len(rq_df) == 0:
            return pd.DataFrame(columns=["trade_date", "close", "daily_return"])

        df = rq_df.reset_index()
        if "date" in df.columns:
            df = df.rename(columns={"date": "trade_date"})
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
        _ensure_init()
        type_map = {"stock": "CS", "etf": "ETF", "index": "INDX"}
        rq_type = type_map.get(asset_type)
        if not rq_type:
            raise ValueError(
                f"Unsupported asset type '{asset_type}' for rqdatac. "
                f"Available: {list(type_map)}"
            )

        kwargs = {"type": rq_type}
        if date:
            kwargs["date"] = date
        instruments = rqdatac.all_instruments(**kwargs)
        if instruments is None or len(instruments) == 0:
            return []

        codes = []
        for oid in instruments["order_book_id"]:
            try:
                codes.append(CodeNormalizer.from_rqdatac(oid))
            except Exception:
                continue
        return sorted(codes)

    def list_universe(
        self,
        universe: str,
        date: str | None = None,
    ) -> list[str]:
        _ensure_init()
        rq_index = UNIVERSE_INDEX_MAP.get(universe)
        if rq_index is None:
            raise ValueError(
                f"Unknown universe '{universe}'. Available: {list(UNIVERSE_INDEX_MAP)}"
            )

        kwargs = {}
        if date:
            kwargs["date"] = date
        components = rqdatac.index_components(rq_index, **kwargs)
        if components is None or len(components) == 0:
            return []

        return sorted(CodeNormalizer.from_rqdatac(c) for c in components)
