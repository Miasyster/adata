"""Tests for store.py — ParquetStore."""

import pandas as pd
import pytest

from adata.schema import DAILY_COLUMNS
from adata.store import ParquetStore

from .conftest import make_daily_df


class TestReadWrite:
    def test_write_and_read(self, tmp_store):
        df = make_daily_df("sh.600519", ["2025-01-02", "2025-01-03"])
        tmp_store.write("sh.600519", df)

        result = tmp_store.read("sh.600519")
        assert result is not None
        assert len(result) == 2
        assert list(result.columns) == DAILY_COLUMNS

    def test_read_nonexistent(self, tmp_store):
        assert tmp_store.read("sh.999999") is None

    def test_write_empty_noop(self, tmp_store):
        tmp_store.write("sh.600519", pd.DataFrame())
        assert tmp_store.read("sh.600519") is None

    def test_write_none_noop(self, tmp_store):
        tmp_store.write("sh.600519", None)
        assert tmp_store.read("sh.600519") is None

    def test_trade_date_is_datetime(self, tmp_store):
        df = make_daily_df("sh.600519", ["2025-01-02"])
        tmp_store.write("sh.600519", df)
        result = tmp_store.read("sh.600519")
        assert pd.api.types.is_datetime64_any_dtype(result["trade_date"])

    def test_category_isolation(self, tmp_store):
        df = make_daily_df("sh.600519", ["2025-01-02"])
        tmp_store.write("sh.600519", df, category="stocks")
        tmp_store.write("sh.600519", df, category="etf")
        assert tmp_store.read("sh.600519", "stocks") is not None
        assert tmp_store.read("sh.600519", "etf") is not None
        assert tmp_store.read("sh.600519", "index") is None


class TestMergeIncremental:
    def test_merge_new_data(self, tmp_store):
        df1 = make_daily_df("sh.600519", ["2025-01-02", "2025-01-03"])
        tmp_store.write("sh.600519", df1)

        df2 = make_daily_df("sh.600519", ["2025-01-06", "2025-01-07"])
        tmp_store.merge_incremental("sh.600519", df2)

        result = tmp_store.read("sh.600519")
        assert len(result) == 4
        dates = result["trade_date"].dt.strftime("%Y-%m-%d").tolist()
        assert dates == ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]

    def test_merge_deduplicates(self, tmp_store):
        df1 = make_daily_df("sh.600519", ["2025-01-02", "2025-01-03"])
        tmp_store.write("sh.600519", df1)

        df2 = make_daily_df("sh.600519", ["2025-01-03", "2025-01-06"])
        tmp_store.merge_incremental("sh.600519", df2)

        result = tmp_store.read("sh.600519")
        assert len(result) == 3

    def test_merge_into_empty(self, tmp_store):
        df = make_daily_df("sh.600519", ["2025-01-02"])
        tmp_store.merge_incremental("sh.600519", df)
        result = tmp_store.read("sh.600519")
        assert len(result) == 1

    def test_merge_empty_noop(self, tmp_store):
        df = make_daily_df("sh.600519", ["2025-01-02"])
        tmp_store.write("sh.600519", df)
        tmp_store.merge_incremental("sh.600519", pd.DataFrame())
        assert len(tmp_store.read("sh.600519")) == 1


class TestLastDate:
    def test_returns_last_date(self, tmp_store):
        df = make_daily_df("sh.600519", ["2025-01-02", "2025-01-06"])
        tmp_store.write("sh.600519", df)
        assert tmp_store.last_date("sh.600519") == "2025-01-06"

    def test_returns_none_if_missing(self, tmp_store):
        assert tmp_store.last_date("sh.999999") is None


class TestListCached:
    def test_lists_cached_codes(self, tmp_store):
        for code in ["sh.600519", "sz.000001"]:
            tmp_store.write(code, make_daily_df(code, ["2025-01-02"]))

        cached = tmp_store.list_cached("stocks")
        assert "sh.600519" in cached
        assert "sz.000001" in cached

    def test_empty_category(self, tmp_store):
        assert tmp_store.list_cached("nonexistent") == []


class TestStats:
    def test_stats_with_data(self, tmp_store):
        tmp_store.write("sh.600519", make_daily_df("sh.600519", ["2025-01-02", "2025-01-03"]))
        tmp_store.write("sz.000001", make_daily_df("sz.000001", ["2025-01-06"]))

        s = tmp_store.stats("stocks")
        assert s["files"] == 2
        assert s["total_rows"] == 3
        assert "2025-01-02" in s["date_range"]
        assert "2025-01-06" in s["date_range"]

    def test_stats_empty(self, tmp_store):
        s = tmp_store.stats("stocks")
        assert s["files"] == 0
        assert s["total_rows"] == 0
