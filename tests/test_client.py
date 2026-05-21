"""Tests for client.py — DataClient."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from adata.client import DataClient
from adata.schema import DAILY_COLUMNS

from .conftest import FakeProvider, make_benchmark_df, make_daily_df


@pytest.fixture
def client_with_fake(tmp_path):
    """DataClient wired to a FakeProvider, no real network calls."""
    provider = FakeProvider()
    provider.seed_daily("sh.600519", [
        "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
    ])
    provider.seed_daily("sz.000001", [
        "2025-01-02", "2025-01-03", "2025-01-06",
    ])
    provider.seed_benchmark("hs300", [
        "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
    ])
    provider.seed_universe("hs300", ["sh.600519", "sz.000001"])

    client = DataClient(data_dir=str(tmp_path))

    with patch.object(client, "_resolve_providers", return_value=[provider]):
        yield client, provider


class TestQueryDaily:
    def test_fetches_and_caches(self, client_with_fake):
        client, provider = client_with_fake
        df = client.query_daily(["sh.600519"], "2025-01-02", "2025-01-08")

        assert len(df) == 5
        assert set(df.columns) == set(DAILY_COLUMNS)
        assert len(provider.fetch_daily_calls) == 1

        df2 = client.query_daily(["sh.600519"], "2025-01-02", "2025-01-08")
        assert len(df2) == 5
        assert len(provider.fetch_daily_calls) == 1

    def test_multiple_codes(self, client_with_fake):
        client, _ = client_with_fake
        df = client.query_daily(["sh.600519", "sz.000001"], "2025-01-02", "2025-01-06")
        codes = df["stock_code"].unique()
        assert "sh.600519" in codes
        assert "sz.000001" in codes

    def test_date_filtering(self, client_with_fake):
        client, _ = client_with_fake
        df = client.query_daily(["sh.600519"], "2025-01-03", "2025-01-06")
        assert len(df) == 2
        assert df["trade_date"].min() == pd.Timestamp("2025-01-03")
        assert df["trade_date"].max() == pd.Timestamp("2025-01-06")

    def test_empty_result(self, client_with_fake):
        client, _ = client_with_fake
        df = client.query_daily(["sh.999999"], "2025-01-01", "2025-01-10")
        assert len(df) == 0
        assert list(df.columns) == DAILY_COLUMNS

    def test_code_normalization(self, client_with_fake):
        client, _ = client_with_fake
        df = client.query_daily(["sh600519"], "2025-01-02", "2025-01-08")
        assert len(df) == 5

    def test_end_date_defaults_to_today(self, client_with_fake):
        client, _ = client_with_fake
        df = client.query_daily(["sh.600519"], "2025-01-01")
        assert len(df) > 0

    def test_no_false_cache_hit(self, client_with_fake):
        """Cache must NOT hit when stored range doesn't cover request."""
        client, provider = client_with_fake
        client.query_daily(["sh.600519"], "2025-01-02", "2025-01-08")
        assert len(provider.fetch_daily_calls) == 1

        client.query_daily(["sh.600519"], "2024-12-01", "2025-01-08")
        assert len(provider.fetch_daily_calls) == 2


class TestQueryBenchmark:
    def test_fetches_benchmark(self, client_with_fake):
        client, provider = client_with_fake
        df = client.query_benchmark("hs300", "2025-01-02", "2025-01-08")
        assert len(df) > 0
        assert "trade_date" in df.columns
        assert "close" in df.columns
        assert "daily_return" in df.columns

    def test_benchmark_caching(self, client_with_fake):
        client, provider = client_with_fake
        client.query_benchmark("hs300", "2025-01-02", "2025-01-08")
        client.query_benchmark("hs300", "2025-01-02", "2025-01-08")
        assert len(provider.fetch_benchmark_calls) == 1

    def test_unknown_benchmark_returns_empty(self, client_with_fake):
        client, _ = client_with_fake
        df = client.query_benchmark("nonexistent", "2025-01-01", "2025-01-10")
        assert len(df) == 0


class TestQueryUniverse:
    def test_returns_codes(self, client_with_fake):
        client, _ = client_with_fake
        codes = client.query_universe("hs300")
        assert "sh.600519" in codes
        assert "sz.000001" in codes

    def test_unknown_universe_returns_empty(self, client_with_fake):
        client, _ = client_with_fake
        codes = client.query_universe("nonexistent")
        assert codes == []


class TestDataStatus:
    def test_status_empty(self, tmp_path):
        client = DataClient(data_dir=str(tmp_path))
        status = client.data_status()
        assert "data_dir" in status
        assert "categories" in status
        assert "providers" in status

    def test_status_with_data(self, client_with_fake):
        client, _ = client_with_fake
        client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")
        status = client.data_status()
        assert "stocks" in status["categories"]
        assert status["categories"]["stocks"]["files"] >= 1


class TestDataFreshness:
    def test_cached_code(self, client_with_fake):
        client, _ = client_with_fake
        client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")
        results = client.data_freshness(["sh.600519"])
        assert len(results) == 1
        assert results[0]["cached"] is True
        assert results[0]["last_date"] is not None

    def test_uncached_code(self, client_with_fake):
        client, _ = client_with_fake
        results = client.data_freshness(["sh.999999"])
        assert len(results) == 1
        assert results[0]["cached"] is False
        assert results[0]["last_date"] is None

    def test_multiple_codes(self, client_with_fake):
        client, _ = client_with_fake
        client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")
        results = client.data_freshness(["sh.600519", "sh.999999"])
        assert len(results) == 2


class TestProviderFallback:
    def test_falls_back_to_next_provider(self, tmp_path):
        """When first provider has no data, falls back to second."""
        empty_provider = FakeProvider()
        empty_provider.name = "empty"

        good_provider = FakeProvider()
        good_provider.name = "good"
        good_provider.seed_daily("sh.600519", ["2025-01-02", "2025-01-03"])

        client = DataClient(data_dir=str(tmp_path))
        with patch.object(client, "_resolve_providers", return_value=[empty_provider, good_provider]):
            df = client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")

        assert len(df) == 2
        assert len(empty_provider.fetch_daily_calls) == 1
        assert len(good_provider.fetch_daily_calls) == 1

    def test_provider_exception_handled(self, tmp_path):
        """Provider raising exception doesn't crash — falls back."""
        class FailingProvider(FakeProvider):
            name = "failing"
            def fetch_daily(self, codes, start_date, end_date):
                raise ConnectionError("Network error")

        failing = FailingProvider()
        good = FakeProvider()
        good.name = "good"
        good.seed_daily("sh.600519", ["2025-01-02"])

        client = DataClient(data_dir=str(tmp_path))
        with patch.object(client, "_resolve_providers", return_value=[failing, good]):
            df = client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")

        assert len(df) == 1


class TestHKQueryDaily:
    @pytest.fixture
    def hk_client(self, tmp_path):
        provider = FakeProvider()
        provider.seed_daily("hk.00700", [
            "2025-01-02", "2025-01-03", "2025-01-06",
        ])
        provider.seed_universe("hsi", ["hk.00700", "hk.09988"])
        client = DataClient(data_dir=str(tmp_path))
        with patch.object(client, "_resolve_providers", return_value=[provider]):
            yield client, provider

    def test_fetches_hk_stock(self, hk_client):
        client, _ = hk_client
        df = client.query_daily(["hk.00700"], "2025-01-02", "2025-01-06", category="hk")
        assert len(df) == 3
        assert df["stock_code"].iloc[0] == "hk.00700"

    def test_hk_code_normalization(self, hk_client):
        client, _ = hk_client
        df = client.query_daily(["00700.XHKG"], "2025-01-02", "2025-01-06", category="hk")
        assert len(df) == 3

    def test_hk_data_status(self, hk_client):
        client, _ = hk_client
        client.query_daily(["hk.00700"], "2025-01-02", "2025-01-06", category="hk")
        status = client.data_status()
        assert "hk" in status["categories"]

    def test_hk_universe(self, hk_client):
        client, _ = hk_client
        codes = client.query_universe("hsi")
        assert "hk.00700" in codes


class TestValidation:
    def test_rejects_missing_required_columns(self, tmp_path):
        """Provider returning data without stock_code should be rejected."""
        bad_provider = FakeProvider()
        bad_provider.name = "bad"
        original_fetch = bad_provider.fetch_daily
        def bad_fetch(codes, start, end):
            df = original_fetch(codes, start, end)
            if len(df) > 0:
                return df.drop(columns=["stock_code"])
            return df
        bad_provider.fetch_daily = bad_fetch
        bad_provider.seed_daily("sh.600519", ["2025-01-02"])

        client = DataClient(data_dir=str(tmp_path))
        with patch.object(client, "_resolve_providers", return_value=[bad_provider]):
            df = client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")
        assert len(df) == 0

    def test_fills_missing_optional_columns(self, tmp_path):
        """Provider returning data without optional columns should fill them."""
        sparse_provider = FakeProvider()
        sparse_provider.name = "sparse"
        original_fetch = sparse_provider.fetch_daily
        def sparse_fetch(codes, start, end, adjust="qfq"):
            df = original_fetch(codes, start, end, adjust=adjust)
            if len(df) > 0:
                return df.drop(columns=["pct_change"])
            return df
        sparse_provider.fetch_daily = sparse_fetch
        sparse_provider.seed_daily("sh.600519", ["2025-01-02"])

        client = DataClient(data_dir=str(tmp_path))
        with patch.object(client, "_resolve_providers", return_value=[sparse_provider]):
            df = client.query_daily(["sh.600519"], "2025-01-01", "2025-01-10")
        assert len(df) == 1
        assert "pct_change" in df.columns
