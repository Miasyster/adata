"""Shared fixtures for adata tests."""

from __future__ import annotations

import pandas as pd
import pytest

from adata.providers.base import BaseProvider
from adata.schema import DAILY_COLUMNS
from adata.store import ParquetStore


def make_daily_df(code: str, dates: list[str]) -> pd.DataFrame:
    """Create a minimal valid daily DataFrame for testing."""
    n = len(dates)
    return pd.DataFrame({
        "trade_date": pd.to_datetime(dates),
        "stock_code": [code] * n,
        "open": [10.0 + i for i in range(n)],
        "high": [11.0 + i for i in range(n)],
        "low": [9.0 + i for i in range(n)],
        "close": [10.5 + i for i in range(n)],
        "volume": [1000.0 * (i + 1) for i in range(n)],
        "amount": [10000.0 * (i + 1) for i in range(n)],
        "pct_change": [1.0 + i * 0.1 for i in range(n)],
    })[DAILY_COLUMNS]


def make_benchmark_df(dates: list[str]) -> pd.DataFrame:
    n = len(dates)
    df = pd.DataFrame({
        "trade_date": pd.to_datetime(dates),
        "close": [3000.0 + i * 10 for i in range(n)],
    })
    df = df.sort_values("trade_date")
    df["daily_return"] = df["close"].pct_change()
    return df[["trade_date", "close", "daily_return"]]


class FakeProvider(BaseProvider):
    """In-memory provider for testing — no network calls."""
    name = "fake"
    supported_asset_types = {"stock", "etf"}

    def __init__(self):
        self._daily_data: dict[str, pd.DataFrame] = {}
        self._benchmark_data: dict[str, pd.DataFrame] = {}
        self._universe_data: dict[str, list[str]] = {}
        self._instruments: dict[str, list[str]] = {}
        self.fetch_daily_calls: list[tuple] = []
        self.fetch_benchmark_calls: list[tuple] = []

    def seed_daily(self, code: str, dates: list[str]):
        self._daily_data[code] = make_daily_df(code, dates)

    def seed_benchmark(self, name: str, dates: list[str]):
        self._benchmark_data[name] = make_benchmark_df(dates)

    def seed_universe(self, universe: str, codes: list[str]):
        self._universe_data[universe] = codes

    def seed_instruments(self, asset_type: str, codes: list[str]):
        self._instruments[asset_type] = codes

    def fetch_daily(self, codes, start_date, end_date):
        self.fetch_daily_calls.append((codes, start_date, end_date))
        dfs = []
        for c in codes:
            if c in self._daily_data:
                df = self._daily_data[c]
                mask = (df["trade_date"] >= pd.Timestamp(start_date)) & (
                    df["trade_date"] <= pd.Timestamp(end_date)
                )
                filtered = df[mask]
                if len(filtered) > 0:
                    dfs.append(filtered)
        if not dfs:
            return pd.DataFrame(columns=DAILY_COLUMNS)
        return pd.concat(dfs, ignore_index=True)

    def fetch_benchmark(self, name, start_date, end_date):
        self.fetch_benchmark_calls.append((name, start_date, end_date))
        if name not in self._benchmark_data:
            raise ValueError(f"Unknown benchmark '{name}'")
        df = self._benchmark_data[name]
        mask = (df["trade_date"] >= pd.Timestamp(start_date)) & (
            df["trade_date"] <= pd.Timestamp(end_date)
        )
        return df[mask].copy()

    def list_instruments(self, asset_type, date=None):
        return self._instruments.get(asset_type, [])

    def list_universe(self, universe, date=None):
        if universe not in self._universe_data:
            raise NotImplementedError(f"Unknown universe '{universe}'")
        return self._universe_data[universe]


@pytest.fixture
def tmp_store(tmp_path):
    """ParquetStore backed by a temporary directory."""
    return ParquetStore(tmp_path)


@pytest.fixture
def fake_provider():
    return FakeProvider()
