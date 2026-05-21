"""Tests for config.py."""

import os
from pathlib import Path
from unittest.mock import patch

from adata.config import BENCHMARK_MAP, UNIVERSE_INDEX_MAP, get_data_dir


class TestGetDataDir:
    def test_default_is_home_adata(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADATA_DIR", None)
            d = get_data_dir()
            assert d == Path.home() / ".adata"
            assert d.is_dir()

    def test_respects_env_var(self, tmp_path):
        custom = tmp_path / "custom_adata"
        with patch.dict(os.environ, {"ADATA_DIR": str(custom)}):
            d = get_data_dir()
            assert d == custom
            assert d.is_dir()


class TestBenchmarkMap:
    def test_has_required_benchmarks(self):
        for name in ("hs300", "zz500", "csi1000", "sz50"):
            assert name in BENCHMARK_MAP
            assert "baostock" in BENCHMARK_MAP[name]
            assert "rqdatac" in BENCHMARK_MAP[name]


class TestHKBenchmarkMap:
    def test_has_hk_benchmarks(self):
        for name in ("hsi", "hscei", "hstech"):
            assert name in BENCHMARK_MAP
            assert "rqdatac" in BENCHMARK_MAP[name]


class TestUniverseIndexMap:
    def test_has_required_universes(self):
        for name in ("hs300", "csi500", "csi1000"):
            assert name in UNIVERSE_INDEX_MAP
            assert UNIVERSE_INDEX_MAP[name] is not None

    def test_has_hk_universes(self):
        for name in ("hsi", "hstech"):
            assert name in UNIVERSE_INDEX_MAP
            assert UNIVERSE_INDEX_MAP[name] is not None
