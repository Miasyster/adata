# adata

**Agent-Native financial data infrastructure for A-shares.**

adata is designed for AI agents, not humans. Agents say *what* data they need — adata handles *where* to get it, *how* to cache it, and *when* to refresh it. Zero configuration, zero data-source knowledge required.

```python
from adata import DataClient

client = DataClient()
df = client.query_daily(["sh.600519", "sz.000001"], "2024-01-01")
# Auto: check cache → fetch missing from best available provider → cache → return DataFrame
```

## Architecture

```
LLM Agent
    ↓ MCP tools (query_daily / query_benchmark / data_status ...)
adata MCP Server
    ↓
DataClient — smart routing layer
    ↓ cache-first → provider fallback chain
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│ Parquet   │ PolarDB  │ rqdatac  │ baostock │ akshare  │
│ (cache)   │          │          │          │          │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

**DataClient** is the single entry point. It transparently:
- Checks local Parquet cache first
- Falls back through a configurable provider chain
- Caches fetched data for future queries
- Normalizes codes across formats (`sh.600519` ↔ `600519.XSHG` ↔ `sh600519`)

**MCP Server** exposes DataClient as MCP tools so any LLM agent can discover and query data through the standard MCP protocol.

## Installation

```bash
pip install -e .

# With specific data providers:
pip install -e ".[rqdatac]"    # 米筐
pip install -e ".[baostock]"   # baostock
pip install -e ".[akshare]"    # 东方财富
pip install -e ".[polardb]"    # Aliyun PolarDB
pip install -e ".[mcp]"        # MCP server

# Everything:
pip install -e ".[all]"
```

## Usage

### Python API (for agents and applications)

```python
from adata import DataClient

client = DataClient()

# Daily OHLCV — auto-routed, auto-cached
df = client.query_daily(["sh.600519"], "2024-01-01")

# Benchmark index
bm = client.query_benchmark("hs300", "2024-01-01")

# Index constituents
codes = client.query_universe("hs300")

# Cache status
status = client.data_status()
# → {"data_dir": "~/.adata", "categories": {"stocks": {"files": 300, ...}}, "providers": [...]}

# Data freshness check
freshness = client.data_freshness(["sh.600519", "sz.000001"])
# → [{"code": "sh.600519", "last_date": "2026-05-14", "stale": false}, ...]
```

### MCP Server (for LLM agents)

```bash
python -m adata mcp    # Start stdio MCP server
```

MCP tools available:

| Tool | Description |
|------|-------------|
| `query_daily` | Query daily OHLCV data |
| `query_benchmark` | Query benchmark index (hs300, zz500, etc.) |
| `query_universe` | List index constituents |
| `data_status` | Cache overview: files, date ranges, providers |
| `data_freshness` | Check data staleness |
| `update_data` | Trigger data update by universe or codes |

Claude Desktop / Claude Code config:

```json
{
  "mcpServers": {
    "adata": {
      "command": "python",
      "args": ["-m", "adata", "mcp"]
    }
  }
}
```

### CLI (for humans)

```bash
# Fetch data from a specific provider
python -m adata fetch --source rqdatac --universe hs300 --mode incremental

# Fetch specific codes
python -m adata fetch --source baostock --codes sh.600519,sz.000001

# Fetch benchmarks
python -m adata fetch --source rqdatac --benchmark hs300,zz500

# Full re-download
python -m adata fetch --source akshare --codes sh.600519 --mode full --start 2015-01-01

# Check cache status
python -m adata status
```

## Data Providers

| Provider | Asset Types | Auth Required | Notes |
|----------|------------|---------------|-------|
| **rqdatac** | Stock, ETF, Index | Yes (`RQDATAC_USERNAME/PASSWORD`) | Fastest, most complete |
| **tushare** | Stock, Index | Yes (`TUSHARE_TOKEN`) | Tushare Pro, batch API |
| **baostock** | Stock | No | Free, sequential per-stock |
| **akshare** | Stock, ETF | No | Free, East Money data |
| **polardb** | Stock, Index | Yes (`POLARDB_PASSWORD`) | Private Aliyun DB |

Provider priority is configurable:

```python
client = DataClient(provider_priority=["rqdatac", "tushare", "baostock", "akshare"])
```

Default: `["polardb", "rqdatac", "tushare", "baostock", "akshare"]`. Unavailable providers are automatically skipped.

## Configuration

Environment variables (or `.env` file):

```bash
# Data directory (default: ~/.adata)
# ADATA_DIR=/path/to/data

# rqdatac
RQDATAC_USERNAME=
RQDATAC_PASSWORD=

# tushare pro (https://tushare.pro)
TUSHARE_TOKEN=

# PolarDB (private)
POLARDB_HOST=
POLARDB_PASSWORD=
```

## Data Schema

**Daily OHLCV** (`trade_date, stock_code, open, high, low, close, volume, amount, pct_change`):

All providers normalize to this schema. Stored as per-instrument Parquet files under `~/.adata/{category}/`.

**Code format**: `{exchange}.{number}` — e.g., `sh.600519`, `sz.000001`. Automatic normalization from rqdatac (`600519.XSHG`), PolarDB (`sh600519`), and raw (`600519`) formats.

## Testing

```bash
pip install pytest
python -m pytest tests/ -v
```

94 tests covering all modules. All tests use in-memory fixtures, no network calls.

## License

MIT
