"""Tests for updater.py — DataUpdater."""

import pandas as pd
import pytest

from adata.updater import DataUpdater, _next_day

from .conftest import FakeProvider, make_daily_df


class TestNextDay:
    def test_normal(self):
        assert _next_day("2025-01-02") == "2025-01-03"

    def test_month_boundary(self):
        assert _next_day("2025-01-31") == "2025-02-01"

    def test_year_boundary(self):
        assert _next_day("2024-12-31") == "2025-01-01"


class TestFetchFull:
    def test_full_fetch(self, tmp_store, fake_provider):
        fake_provider.seed_daily("sh.600519", ["2025-01-02", "2025-01-03", "2025-01-06"])
        updater = DataUpdater(fake_provider, tmp_store)

        result = updater.fetch(
            codes=["sh.600519"],
            start_date="2025-01-01",
            end_date="2025-01-10",
            mode="full",
        )
        assert result.fetched == 1
        stored = tmp_store.read("sh.600519")
        assert len(stored) == 3

    def test_full_overwrites(self, tmp_store, fake_provider):
        old = make_daily_df("sh.600519", ["2020-01-01"])
        tmp_store.write("sh.600519", old)

        fake_provider.seed_daily("sh.600519", ["2025-01-02", "2025-01-03"])
        updater = DataUpdater(fake_provider, tmp_store)

        updater.fetch(codes=["sh.600519"], start_date="2025-01-01", end_date="2025-01-10", mode="full")
        stored = tmp_store.read("sh.600519")
        assert len(stored) == 2
        assert stored["trade_date"].min() == pd.Timestamp("2025-01-02")


class TestFetchIncremental:
    def test_incremental_from_scratch(self, tmp_store, fake_provider):
        fake_provider.seed_daily("sh.600519", ["2025-01-02", "2025-01-03"])
        updater = DataUpdater(fake_provider, tmp_store)

        result = updater.fetch(codes=["sh.600519"], end_date="2025-01-10", mode="incremental")
        assert result.fetched == 1

    def test_incremental_appends(self, tmp_store, fake_provider):
        tmp_store.write("sh.600519", make_daily_df("sh.600519", ["2025-01-02", "2025-01-03"]))
        fake_provider.seed_daily("sh.600519", ["2025-01-06", "2025-01-07"])
        updater = DataUpdater(fake_provider, tmp_store)

        result = updater.fetch(codes=["sh.600519"], end_date="2025-01-10", mode="incremental")
        assert result.fetched == 1
        stored = tmp_store.read("sh.600519")
        assert len(stored) == 4

    def test_incremental_skips_up_to_date(self, tmp_store, fake_provider):
        tmp_store.write("sh.600519", make_daily_df("sh.600519", ["2025-01-02"]))
        updater = DataUpdater(fake_provider, tmp_store)

        result = updater.fetch(codes=["sh.600519"], end_date="2025-01-02", mode="incremental")
        assert result.skipped == 1
        assert result.fetched == 0

    def test_invalid_mode_raises(self, tmp_store, fake_provider):
        updater = DataUpdater(fake_provider, tmp_store)
        with pytest.raises(ValueError, match="Unknown mode"):
            updater.fetch(codes=["sh.600519"], mode="bad")


class TestFetchByUniverse:
    def test_fetch_universe(self, tmp_store, fake_provider):
        fake_provider.seed_universe("hs300", ["sh.600519", "sz.000001"])
        fake_provider.seed_daily("sh.600519", ["2025-01-02"])
        fake_provider.seed_daily("sz.000001", ["2025-01-02"])
        updater = DataUpdater(fake_provider, tmp_store)

        result = updater.fetch_by_universe("hs300", end_date="2025-01-10")
        assert result.fetched == 2

    def test_empty_universe(self, tmp_store, fake_provider):
        fake_provider.seed_universe("empty", [])
        updater = DataUpdater(fake_provider, tmp_store)
        result = updater.fetch_by_universe("empty", end_date="2025-01-10")
        assert result.total == 0


class TestFetchBenchmarks:
    def test_fetch_benchmark(self, tmp_store, fake_provider):
        fake_provider.seed_benchmark("hs300", ["2025-01-02", "2025-01-03", "2025-01-06"])
        updater = DataUpdater(fake_provider, tmp_store)

        result = updater.fetch_benchmarks(["hs300"])
        assert result.fetched == 1
        stored = tmp_store.read("benchmark_hs300", "benchmark")
        assert len(stored) == 3

    def test_unknown_benchmark(self, tmp_store, fake_provider):
        updater = DataUpdater(fake_provider, tmp_store)
        result = updater.fetch_benchmarks(["nonexistent"])
        assert result.failed == 1
