"""DataClient — agent-native smart data layer.

The single entry point for agents. Handles caching, provider routing,
and data freshness transparently.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .config import get_data_dir
from .providers import get_provider, list_providers
from .providers.base import BaseProvider
from .schema import DAILY_COLUMNS, CodeNormalizer
from .store import ParquetStore

logger = logging.getLogger(__name__)

_DEFAULT_PRIORITY = ["polardb", "rqdatac", "tushare", "baostock", "akshare"]

_CATEGORY_ASSET_TYPE = {
    "stocks": "stock",
    "etf": "etf",
    "index": "index",
}


class DataClient:
    def __init__(
        self,
        data_dir: str | None = None,
        provider_priority: list[str] | None = None,
    ):
        self.store = ParquetStore(data_dir or get_data_dir())
        self._priority = provider_priority or _DEFAULT_PRIORITY

    def query_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str | None = None,
        category: str = "stocks",
    ) -> pd.DataFrame:
        codes = [CodeNormalizer.normalize(c) for c in codes]
        end_date = end_date or date.today().isoformat()

        cached_dfs, missing = self._check_cache(codes, start_date, end_date, category)

        if missing:
            asset_type = _CATEGORY_ASSET_TYPE.get(category, "stock")
            self._fetch_missing(missing, start_date, end_date, category, asset_type)
            fresh_dfs = self._read_codes(missing, start_date, end_date, category)
            cached_dfs.extend(fresh_dfs)

        if not cached_dfs:
            return pd.DataFrame(columns=DAILY_COLUMNS)
        return pd.concat(cached_dfs, ignore_index=True).sort_values(["stock_code", "trade_date"])

    def query_benchmark(
        self,
        name: str,
        start_date: str,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        end_date = end_date or date.today().isoformat()
        bm_code = f"benchmark_{name}"

        cached = self.store.read(bm_code, "benchmark")
        if cached is not None and len(cached) > 0:
            lo = cached["trade_date"].min()
            hi = cached["trade_date"].max()
            req_start = pd.Timestamp(start_date)
            req_end = pd.Timestamp(end_date)
            if lo <= req_start and hi >= req_end:
                mask = (cached["trade_date"] >= req_start) & (cached["trade_date"] <= req_end)
                return cached[mask].reset_index(drop=True)

        for provider in self._resolve_providers():
            try:
                df = provider.fetch_benchmark(name, start_date, end_date)
                if df is not None and len(df) > 0:
                    self.store.write(bm_code, df, "benchmark")
                    logger.info("Benchmark '%s' fetched via %s: %d rows", name, provider.name, len(df))
                    return df
            except Exception as e:
                logger.warning("Benchmark '%s' failed on %s: %s", name, provider.name, e)
                continue

        if cached is not None and len(cached) > 0:
            return cached
        return pd.DataFrame(columns=["trade_date", "close", "daily_return"])

    def query_universe(
        self,
        universe: str,
        date_str: str | None = None,
    ) -> list[str]:
        for provider in self._resolve_providers():
            try:
                codes = provider.list_universe(universe, date=date_str)
                if codes:
                    return codes
            except (NotImplementedError, ValueError):
                continue
            except Exception as e:
                logger.warning("Universe '%s' failed on %s: %s", universe, provider.name, e)
                continue
        return []

    def data_status(self, category: str | None = None) -> dict:
        categories = [category] if category else ["stocks", "etf", "index", "benchmark"]
        cat_stats = {}
        for cat in categories:
            cat_dir = self.store.data_dir / cat
            if not cat_dir.is_dir():
                continue
            s = self.store.stats(cat)
            if s["files"] > 0:
                cat_stats[cat] = s

        return {
            "data_dir": str(self.store.data_dir),
            "categories": cat_stats,
            "providers": self._available_provider_names(),
        }

    def data_freshness(
        self,
        codes: list[str],
        category: str = "stocks",
    ) -> list[dict]:
        codes = [CodeNormalizer.normalize(c) for c in codes]
        today_str = date.today().isoformat()
        today_dt = date.today()
        results = []

        for code in codes:
            last = self.store.last_date(code, category)
            if last is None:
                results.append({"code": code, "last_date": None, "cached": False})
                continue

            last_dt = date.fromisoformat(last)
            gap = (today_dt - last_dt).days
            stale = gap > 3
            entry = {"code": code, "last_date": last, "cached": True, "stale": stale}
            if stale:
                entry["gap_days"] = gap
            results.append(entry)

        return results

    def _check_cache(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        category: str,
    ) -> tuple[list[pd.DataFrame], list[str]]:
        cached_dfs = []
        missing = []
        req_start = pd.Timestamp(start_date)
        req_end = pd.Timestamp(end_date)

        for code in codes:
            df = self.store.read(code, category)
            if df is not None and len(df) > 0:
                lo = df["trade_date"].min()
                hi = df["trade_date"].max()
                if lo <= req_start and hi >= req_end:
                    mask = (df["trade_date"] >= req_start) & (df["trade_date"] <= req_end)
                    filtered = df[mask]
                    if len(filtered) > 0:
                        cached_dfs.append(filtered)
                        continue
            missing.append(code)

        return cached_dfs, missing

    def _fetch_missing(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        category: str,
        asset_type: str,
    ):
        remaining = list(codes)

        for provider in self._resolve_providers():
            if not remaining:
                break
            if not provider.supports(asset_type):
                continue
            try:
                logger.info("Fetching %d codes via %s", len(remaining), provider.name)
                batch_size = 500 if provider.name == "polardb" else 200
                for i in range(0, len(remaining), batch_size):
                    chunk = remaining[i : i + batch_size]
                    df = provider.fetch_daily(chunk, start_date, end_date)
                    if df is not None and len(df) > 0:
                        df = self._validate_daily(df, provider.name)
                        if df is not None and len(df) > 0:
                            for code, group in df.groupby("stock_code"):
                                self.store.merge_incremental(code, group, category)
                            fetched = set(df["stock_code"].unique())
                            remaining = [c for c in remaining if c not in fetched]
            except Exception as e:
                logger.warning("Provider %s failed for %d codes: %s", provider.name, len(remaining), e)
                continue

        if remaining:
            logger.warning("Could not fetch %d codes from any provider: %s", len(remaining), remaining[:5])

    def _read_codes(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        category: str,
    ) -> list[pd.DataFrame]:
        req_start = pd.Timestamp(start_date)
        req_end = pd.Timestamp(end_date)
        dfs = []

        for code in codes:
            df = self.store.read(code, category)
            if df is not None and len(df) > 0:
                mask = (df["trade_date"] >= req_start) & (df["trade_date"] <= req_end)
                filtered = df[mask]
                if len(filtered) > 0:
                    dfs.append(filtered)

        return dfs

    @staticmethod
    def _validate_daily(df: pd.DataFrame, provider_name: str) -> pd.DataFrame | None:
        required = {"trade_date", "stock_code"}
        missing_cols = required - set(df.columns)
        if missing_cols:
            logger.error("Provider %s returned data missing columns: %s", provider_name, missing_cols)
            return None
        for col in DAILY_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[DAILY_COLUMNS]

    def _resolve_providers(self) -> list[BaseProvider]:
        providers = []
        for name in self._priority:
            if name not in list_providers():
                continue
            try:
                p = get_provider(name)
                providers.append(p)
            except Exception:
                continue
        return providers

    def _available_provider_names(self) -> list[str]:
        available = []
        for name in self._priority:
            if name in list_providers():
                available.append(name)
        return available
