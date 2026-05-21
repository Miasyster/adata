"""Tests for mcp_server.py — MCP tool functions."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from adata.client import DataClient
from adata.mcp_server import (
    _get_client,
    data_freshness,
    data_status,
    query_benchmark,
    query_daily,
    query_universe,
    update_data,
)

from .conftest import FakeProvider, make_daily_df


@pytest.fixture(autouse=True)
def reset_mcp_client():
    """Reset the module-level client between tests."""
    import adata.mcp_server as mod
    mod._client = None
    yield
    mod._client = None


@pytest.fixture
def mcp_client(tmp_path):
    """Set up MCP module-level client with FakeProvider."""
    import adata.mcp_server as mod

    provider = FakeProvider()
    provider.seed_daily("sh.600519", [
        "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
    ])
    provider.seed_daily("sz.000001", ["2025-01-02", "2025-01-03"])
    provider.seed_daily("hk.00700", ["2025-01-02", "2025-01-03", "2025-01-06"])
    provider.seed_benchmark("hs300", [
        "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07",
    ])
    provider.seed_universe("hs300", ["sh.600519", "sz.000001"])
    provider.seed_universe("hsi", ["hk.00700", "hk.09988"])

    client = DataClient(data_dir=str(tmp_path))
    mod._client = client

    with patch.object(client, "_resolve_providers", return_value=[provider]):
        yield client, provider


class TestQueryDailyTool:
    def test_returns_json(self, mcp_client):
        result = json.loads(query_daily("sh.600519", "2025-01-02", "2025-01-08"))
        assert result["rows"] == 5
        assert "sh.600519" in result["codes"]
        assert "date_range" in result

    def test_multiple_codes(self, mcp_client):
        result = json.loads(query_daily("sh.600519,sz.000001", "2025-01-02", "2025-01-06"))
        assert result["rows"] > 0
        assert len(result["codes"]) == 2

    def test_small_result_has_data_field(self, mcp_client):
        result = json.loads(query_daily("sh.600519", "2025-01-02", "2025-01-03"))
        assert "data" in result
        assert len(result["data"]) == 2

    def test_large_result_has_head_tail(self, mcp_client):
        result = json.loads(query_daily("sh.600519", "2025-01-02", "2025-01-08"))
        assert result["rows"] == 5
        assert "head" in result or "data" in result

    def test_empty_codes_error(self, mcp_client):
        result = json.loads(query_daily("", "2025-01-01"))
        assert "error" in result

    def test_no_data(self, mcp_client):
        result = json.loads(query_daily("sh.999999", "2025-01-01", "2025-01-10"))
        assert result["rows"] == 0


class TestQueryBenchmarkTool:
    def test_returns_json(self, mcp_client):
        result = json.loads(query_benchmark("hs300", "2025-01-02", "2025-01-07"))
        assert result["rows"] > 0
        assert result["benchmark"] == "hs300"

    def test_no_data(self, mcp_client):
        result = json.loads(query_benchmark("nonexistent", "2025-01-01", "2025-01-10"))
        assert result["rows"] == 0


class TestQueryUniverseTool:
    def test_returns_codes(self, mcp_client):
        result = json.loads(query_universe("hs300"))
        assert result["count"] == 2
        assert "sh.600519" in result["codes"]

    def test_unknown_universe(self, mcp_client):
        result = json.loads(query_universe("nonexistent"))
        assert result["count"] == 0


class TestDataStatusTool:
    def test_returns_structure(self, mcp_client):
        result = json.loads(data_status())
        assert "data_dir" in result
        assert "providers" in result
        assert "categories" in result


class TestDataFreshnessTool:
    def test_uncached(self, mcp_client):
        result = json.loads(data_freshness("sh.600519"))
        assert len(result) == 1
        assert result[0]["cached"] is False

    def test_after_fetch(self, mcp_client):
        query_daily("sh.600519", "2025-01-01", "2025-01-10")
        result = json.loads(data_freshness("sh.600519"))
        assert result[0]["cached"] is True

    def test_empty_codes_error(self, mcp_client):
        result = json.loads(data_freshness(""))
        assert "error" in result


class TestUpdateDataTool:
    def test_update_by_codes(self, mcp_client):
        result = json.loads(update_data(codes="sh.600519", start_date="2025-01-02", end_date="2025-01-08"))
        assert result["updated"] is True
        assert result["codes_requested"] == 1
        assert result["rows_available"] > 0

    def test_update_by_universe(self, mcp_client):
        result = json.loads(update_data(universe="hs300", start_date="2025-01-02", end_date="2025-01-06"))
        assert result["updated"] is True
        assert result["codes_requested"] == 2

    def test_no_target_error(self, mcp_client):
        result = json.loads(update_data())
        assert "error" in result


class TestHKQueryDailyTool:
    def test_hk_query(self, mcp_client):
        result = json.loads(query_daily("hk.00700", "2025-01-02", "2025-01-06", category="hk"))
        assert result["rows"] == 3
        assert "hk.00700" in result["codes"]

    def test_hk_universe(self, mcp_client):
        result = json.loads(query_universe("hsi"))
        assert result["count"] == 2
        assert "hk.00700" in result["codes"]


class TestMCPToolRegistration:
    def test_tools_registered(self):
        from adata.mcp_server import mcp
        tools = mcp._tool_manager.list_tools()
        tool_names = {t.name for t in tools}
        expected = {"query_daily", "query_benchmark", "query_universe", "data_status", "data_freshness", "update_data"}
        assert expected == tool_names
