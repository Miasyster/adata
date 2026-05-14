"""Base provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseProvider(ABC):
    name: str = ""
    supported_asset_types: set[str] = set()

    @abstractmethod
    def fetch_daily(
        self, codes: list[str], start_date: str, end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Fetch daily OHLCV. Returns DataFrame with standard DAILY_COLUMNS.

        adjust: 'qfq' (forward-adjusted, default), 'hfq' (backward), 'none'.
        """

    @abstractmethod
    def fetch_benchmark(
        self, name: str, start_date: str, end_date: str,
    ) -> pd.DataFrame:
        """Fetch benchmark index. Returns DataFrame with BENCHMARK_COLUMNS."""

    @abstractmethod
    def list_instruments(
        self, asset_type: str, date: str | None = None,
    ) -> list[str]:
        """List available instrument codes for the given asset type."""

    @abstractmethod
    def list_universe(
        self, universe: str, date: str | None = None,
    ) -> list[str]:
        """List constituent codes of a named universe (e.g. hs300)."""

    def supports(self, asset_type: str) -> bool:
        return asset_type in self.supported_asset_types
