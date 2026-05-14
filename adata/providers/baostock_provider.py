"""baostock provider — free A-share data (single-stock sequential)."""

from __future__ import annotations

import logging
import threading
import time

import pandas as pd

from ..config import BENCHMARK_MAP
from ..schema import DAILY_COLUMNS, CodeNormalizer
from . import register
from .base import BaseProvider

logger = logging.getLogger(__name__)

_bs_lock = threading.Lock()
_bs_depth = 0

try:
    import baostock as bs

    _HAS_BS = True
except ImportError:
    _HAS_BS = False
    bs = None  # type: ignore[assignment]


def _ensure_installed():
    if not _HAS_BS:
        raise RuntimeError("baostock is not installed. Run: pip install baostock")


def _login():
    global _bs_depth
    _bs_depth += 1
    if _bs_depth > 1:
        return
    for attempt in range(3):
        try:
            lg = bs.login()
            if lg.error_code == "0":
                return
            if attempt < 2:
                logger.warning("baostock login attempt %d failed: %s", attempt + 1, lg.error_msg)
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"baostock login failed: {lg.error_msg}")
        except RuntimeError:
            raise
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"baostock login error: {e}")


def _logout():
    global _bs_depth
    _bs_depth -= 1
    if _bs_depth > 0:
        return
    try:
        bs.logout()
    except Exception:
        pass


def _query_to_df(rs) -> pd.DataFrame | None:
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    return pd.DataFrame(rows, columns=rs.fields)


def _fetch_one(code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Fetch single stock daily OHLCV (must be called inside login session)."""
    rs = bs.query_history_k_data_plus(
        code,
        "date,code,open,high,low,close,volume,amount,pctChg",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )
    df = _query_to_df(rs)
    if df is None:
        return None

    df = df.rename(columns={
        "date": "trade_date",
        "code": "stock_code",
        "pctChg": "pct_change",
    })
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for col in ("open", "high", "low", "close", "volume", "amount", "pct_change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if df["pct_change"].isna().all():
        df["pct_change"] = df["close"].pct_change() * 100
    return df[DAILY_COLUMNS].sort_values("trade_date")


@register
class BaostockProvider(BaseProvider):
    name = "baostock"
    supported_asset_types = {"stock"}

    def fetch_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        _ensure_installed()
        all_dfs: list[pd.DataFrame] = []

        with _bs_lock:
            _login()
            try:
                for i, raw_code in enumerate(codes):
                    code = CodeNormalizer.to_baostock(raw_code)
                    try:
                        df = _fetch_one(code, start_date, end_date)
                        if df is not None and len(df) > 0:
                            all_dfs.append(df)
                    except Exception as e:
                        logger.warning("baostock fetch failed for %s: %s", code, e)
                    if (i + 1) % 50 == 0:
                        logger.info("baostock progress: %d/%d", i + 1, len(codes))
            finally:
                _logout()

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
        info = BENCHMARK_MAP.get(name)
        if not info or "baostock" not in info:
            raise ValueError(f"Unknown benchmark '{name}' for baostock")

        bs_code = info["baostock"]
        with _bs_lock:
            _login()
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,close",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="2",
                )
                df = _query_to_df(rs)
            finally:
                _logout()

        if df is None:
            return pd.DataFrame(columns=["trade_date", "close", "daily_return"])

        df["trade_date"] = pd.to_datetime(df["date"])
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
        if asset_type != "stock":
            raise ValueError(f"baostock only supports asset_type='stock', got '{asset_type}'")

        from datetime import datetime
        date = date or datetime.now().strftime("%Y-%m-%d")

        with _bs_lock:
            _login()
            try:
                rs = bs.query_all_stock(day=date)
                df = _query_to_df(rs)
            finally:
                _logout()

        if df is None:
            return []
        codes = []
        for code in df["code"]:
            if code.startswith("sh.000") or code.startswith("bj."):
                continue
            codes.append(code)
        return sorted(codes)

    def list_universe(
        self,
        universe: str,
        date: str | None = None,
    ) -> list[str]:
        _ensure_installed()
        from datetime import datetime
        date = date or datetime.now().strftime("%Y-%m-%d")

        if universe in ("hs300", "csi500", "zz500"):
            return self._fetch_index_bs(universe, date)
        if universe == "csi1000":
            return self._derive_exclusion(date, top_n=1000)
        if universe == "csi2000":
            return self._derive_exclusion(date, top_n=2000)
        raise ValueError(f"Unknown universe '{universe}' for baostock")

    def _fetch_index_bs(self, name: str, date: str) -> list[str]:
        with _bs_lock:
            _login()
            try:
                if name == "hs300":
                    rs = bs.query_hs300_stocks(date)
                else:
                    rs = bs.query_zz500_stocks(date)
                codes = []
                while rs.error_code == "0" and rs.next():
                    row = rs.get_row_data()
                    codes.append(row[1])
            finally:
                _logout()
        return sorted(codes)

    def _derive_exclusion(self, date: str, top_n: int) -> list[str]:
        hs300 = set(self._fetch_index_bs("hs300", date))
        csi500 = set(self._fetch_index_bs("csi500", date))
        exclude = hs300 | csi500

        if top_n > 1000:
            csi1000 = set(self._derive_exclusion(date, 1000))
            exclude |= csi1000

        all_stocks = self.list_instruments("stock", date)
        remaining = [c for c in all_stocks if c not in exclude]
        return remaining[:top_n]
