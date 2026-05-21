"""Tests for schema.py — CodeNormalizer."""

import pytest

from adata.schema import DAILY_COLUMNS, CodeNormalizer


class TestCodeNormalize:
    def test_baostock_format(self):
        assert CodeNormalizer.normalize("sh.600519") == "sh.600519"
        assert CodeNormalizer.normalize("sz.000001") == "sz.000001"

    def test_no_dot_prefix(self):
        assert CodeNormalizer.normalize("sh600519") == "sh.600519"
        assert CodeNormalizer.normalize("sz000001") == "sz.000001"

    def test_rqdatac_format(self):
        assert CodeNormalizer.normalize("600519.XSHG") == "sh.600519"
        assert CodeNormalizer.normalize("000001.XSHE") == "sz.000001"

    def test_uppercase_prefix(self):
        assert CodeNormalizer.normalize("SH.600519") == "sh.600519"
        assert CodeNormalizer.normalize("SZ.000001") == "sz.000001"

    def test_whitespace_stripped(self):
        assert CodeNormalizer.normalize("  sh.600519  ") == "sh.600519"

    def test_unknown_fallback(self):
        result = CodeNormalizer.normalize("UNKNOWN")
        assert result == "unknown"


class TestHKCodeNormalize:
    def test_hk_dot_format(self):
        assert CodeNormalizer.normalize("hk.00700") == "hk.00700"
        assert CodeNormalizer.normalize("hk.09988") == "hk.09988"

    def test_hk_uppercase(self):
        assert CodeNormalizer.normalize("HK.00700") == "hk.00700"

    def test_hk_rqdatac_format(self):
        assert CodeNormalizer.normalize("00700.XHKG") == "hk.00700"
        assert CodeNormalizer.normalize("09988.XHKG") == "hk.09988"

    def test_hk_no_dot(self):
        assert CodeNormalizer.normalize("hk00700") == "hk.00700"

    def test_hk_suffix_format(self):
        assert CodeNormalizer.normalize("00700.HK") == "hk.00700"

    def test_a_share_still_works(self):
        assert CodeNormalizer.normalize("sh.600519") == "sh.600519"
        assert CodeNormalizer.normalize("600519.XSHG") == "sh.600519"


class TestToRqdatac:
    def test_sh(self):
        assert CodeNormalizer.to_rqdatac("sh.600519") == "600519.XSHG"

    def test_sz(self):
        assert CodeNormalizer.to_rqdatac("sz.000001") == "000001.XSHE"

    def test_hk(self):
        assert CodeNormalizer.to_rqdatac("hk.00700") == "00700.XHKG"

    def test_from_rqdatac_format(self):
        assert CodeNormalizer.to_rqdatac("600519.XSHG") == "600519.XSHG"


class TestToBaostock:
    def test_identity(self):
        assert CodeNormalizer.to_baostock("sh.600519") == "sh.600519"

    def test_from_rqdatac(self):
        assert CodeNormalizer.to_baostock("600519.XSHG") == "sh.600519"


class TestParquetName:
    def test_to_parquet_name(self):
        assert CodeNormalizer.to_parquet_name("sh.600519") == "sh_600519"

    def test_from_parquet_name(self):
        assert CodeNormalizer.from_parquet_name("sh_600519") == "sh.600519"
        assert CodeNormalizer.from_parquet_name("sh_600519.parquet") == "sh.600519"

    def test_hk_to_parquet_name(self):
        assert CodeNormalizer.to_parquet_name("hk.00700") == "hk_00700"

    def test_hk_from_parquet_name(self):
        assert CodeNormalizer.from_parquet_name("hk_00700") == "hk.00700"
        assert CodeNormalizer.from_parquet_name("hk_00700.parquet") == "hk.00700"

    def test_roundtrip(self):
        code = "sz.000001"
        pname = CodeNormalizer.to_parquet_name(code)
        assert CodeNormalizer.from_parquet_name(pname) == code

    def test_hk_roundtrip(self):
        code = "hk.00700"
        pname = CodeNormalizer.to_parquet_name(code)
        assert CodeNormalizer.from_parquet_name(pname) == code


class TestFromRqdatac:
    def test_xshg(self):
        assert CodeNormalizer.from_rqdatac("600519.XSHG") == "sh.600519"

    def test_xshe(self):
        assert CodeNormalizer.from_rqdatac("000001.XSHE") == "sz.000001"

    def test_xhkg(self):
        assert CodeNormalizer.from_rqdatac("00700.XHKG") == "hk.00700"

    def test_unknown_suffix(self):
        assert CodeNormalizer.from_rqdatac("ABC.XYZ") == "ABC.XYZ"


class TestDailyColumns:
    def test_required_columns(self):
        expected = {"trade_date", "stock_code", "open", "high", "low", "close", "volume", "amount", "pct_change"}
        assert set(DAILY_COLUMNS) == expected
