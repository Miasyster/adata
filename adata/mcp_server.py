"""FastMCP server for agent-native financial data access.

Exposes DataClient capabilities as MCP tools so any LLM agent
can discover and query A-share market data through the MCP protocol.
"""

from __future__ import annotations

import json
import logging
import threading

from mcp.server.fastmcp import FastMCP

from .client import DataClient
from .schema import CodeNormalizer

logger = logging.getLogger(__name__)


def _error(code: str, message: str) -> str:
    return json.dumps({"error": message, "error_code": code}, ensure_ascii=False)

mcp = FastMCP(
    "adata",
    instructions=(
        "adata — A 股金融数据基建。查询日线行情、基准指数、股票池成分。"
        "数据自动缓存，智能路由多数据源（PolarDB → rqdatac → baostock → akshare）。"
    ),
)

_client: DataClient | None = None
_client_lock = threading.Lock()


def _get_client() -> DataClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = DataClient()
    return _client


@mcp.tool()
def query_daily(
    codes: str,
    start_date: str,
    end_date: str = "",
    category: str = "stocks",
) -> str:
    """查询 A 股日线数据（OHLCV + 涨跌幅）。

    自动从缓存或数据源获取，无需指定数据源。

    Args:
        codes: 股票代码，逗号分隔，如 'sh.600519,sz.000001'
        start_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD（默认今天）
        category: 品种类型 stocks/etf/index
    """
    client = _get_client()
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return _error("EMPTY_CODES", "codes 不能为空")

    df = client.query_daily(
        code_list,
        start_date,
        end_date=end_date or None,
        category=category,
    )

    if df is None or len(df) == 0:
        return json.dumps({"rows": 0, "message": "无数据"})

    summary = {
        "rows": len(df),
        "codes": sorted(df["stock_code"].unique().tolist()),
        "date_range": f"{df['trade_date'].min().strftime('%Y-%m-%d')} ~ {df['trade_date'].max().strftime('%Y-%m-%d')}",
        "columns": df.columns.tolist(),
    }

    if len(df) <= 50:
        summary["data"] = json.loads(df.to_json(orient="records", date_format="iso"))
    else:
        summary["head"] = json.loads(df.head(10).to_json(orient="records", date_format="iso"))
        summary["tail"] = json.loads(df.tail(10).to_json(orient="records", date_format="iso"))

    return json.dumps(summary, ensure_ascii=False, default=str)


@mcp.tool()
def query_benchmark(
    name: str,
    start_date: str,
    end_date: str = "",
) -> str:
    """查询基准指数日线（收盘价 + 日收益率）。

    Args:
        name: 基准名称 hs300/zz500/csi500/csi1000/sz50
        start_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD（默认今天）
    """
    client = _get_client()
    df = client.query_benchmark(name, start_date, end_date=end_date or None)

    if df is None or len(df) == 0:
        return json.dumps({"rows": 0, "message": "无数据"})

    summary = {
        "rows": len(df),
        "benchmark": name,
        "date_range": f"{df['trade_date'].min().strftime('%Y-%m-%d')} ~ {df['trade_date'].max().strftime('%Y-%m-%d')}",
    }

    if len(df) <= 50:
        summary["data"] = json.loads(df.to_json(orient="records", date_format="iso"))
    else:
        summary["head"] = json.loads(df.head(10).to_json(orient="records", date_format="iso"))
        summary["tail"] = json.loads(df.tail(10).to_json(orient="records", date_format="iso"))

    return json.dumps(summary, ensure_ascii=False, default=str)


@mcp.tool()
def query_universe(
    universe: str,
    date: str = "",
) -> str:
    """查询股票池成分列表。

    Args:
        universe: 股票池名称 hs300/csi500/csi1000/csi2000
        date: 日期 YYYY-MM-DD（默认今天）
    """
    client = _get_client()
    codes = client.query_universe(universe, date_str=date or None)

    return json.dumps({
        "universe": universe,
        "count": len(codes),
        "codes": codes,
    }, ensure_ascii=False)


@mcp.tool()
def data_status(category: str = "") -> str:
    """查看当前数据缓存状态：覆盖范围、数据量、可用数据源。

    Args:
        category: 品种类型过滤 stocks/etf/index/benchmark（默认全部）
    """
    client = _get_client()
    status = client.data_status(category=category or None)
    return json.dumps(status, ensure_ascii=False, default=str)


@mcp.tool()
def data_freshness(codes: str, category: str = "stocks") -> str:
    """检查指定股票数据的新鲜度（最新日期、是否过期）。

    Args:
        codes: 股票代码，逗号分隔
        category: 品种类型 stocks/etf/index
    """
    client = _get_client()
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        return _error("EMPTY_CODES", "codes 不能为空")

    results = client.data_freshness(code_list, category=category)
    return json.dumps(results, ensure_ascii=False)


@mcp.tool()
def update_data(
    universe: str = "",
    codes: str = "",
    category: str = "stocks",
    start_date: str = "2015-01-01",
    end_date: str = "",
) -> str:
    """手动触发数据更新。可指定股票池或具体代码。

    数据通过 provider 链自动获取并缓存到本地。

    Args:
        universe: 股票池名称（如 hs300），与 codes 二选一
        codes: 逗号分隔的股票代码，与 universe 二选一
        category: 品种类型 stocks/etf/index
        start_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD（默认今天）
    """
    client = _get_client()

    if universe:
        code_list = client.query_universe(universe)
        if not code_list:
            return _error("UNIVERSE_EMPTY", f"无法获取股票池 '{universe}' 的成分")
    elif codes:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        return _error("MISSING_PARAM", "请指定 universe 或 codes")

    df = client.query_daily(
        code_list,
        start_date,
        end_date=end_date or None,
        category=category,
    )

    return json.dumps({
        "updated": True,
        "codes_requested": len(code_list),
        "rows_available": len(df) if df is not None else 0,
        "category": category,
    }, ensure_ascii=False)
