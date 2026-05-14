"""PolarDB provider — Aliyun PolarDB (MySQL-compatible) company database."""

from __future__ import annotations

import logging
import os
import threading

import pandas as pd

from ..schema import DAILY_COLUMNS, CodeNormalizer
from . import register
from .base import BaseProvider

logger = logging.getLogger(__name__)

_REQUIRED_ENV = ("POLARDB_HOST", "POLARDB_PASSWORD")
_OPTIONAL_ENV_DEFAULTS = {
    "POLARDB_PORT": "3306",
    "POLARDB_USER": "readonly",
    "POLARDB_DB": "one_platform",
}

_BENCHMARK_CODES = {
    "hs300": "000300",
    "zz500": "000905",
    "csi500": "000905",
    "csi1000": "000852",
    "sz50": "000016",
    "csi2000": "399303",
}

_conn_lock = threading.Lock()
_conn = None


def _to_polardb_code(code: str) -> str:
    """sh.600519 → 600519"""
    code = CodeNormalizer.normalize(code)
    parts = code.split(".", 1)
    return parts[1] if len(parts) == 2 else code


def _from_polardb(code_col, full_code_col) -> str:
    """(600519, sh600519) → sh.600519"""
    fc = str(full_code_col) if full_code_col else ""
    for pfx in ("sh", "sz", "bj"):
        if fc.startswith(pfx):
            return f"{pfx}.{fc[len(pfx):]}"
    return str(code_col)


def _get_conn():
    global _conn
    import pymysql

    with _conn_lock:
        if _conn is not None:
            try:
                _conn.ping(reconnect=True)
                return _conn
            except Exception:
                _conn = None

        missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"Required environment variables not set: {', '.join(missing)}"
            )

        creds = {k: os.environ.get(k, v) for k, v in _OPTIONAL_ENV_DEFAULTS.items()}
        pwd = os.environ["POLARDB_PASSWORD"]
        _conn = pymysql.connect(
            host=os.environ["POLARDB_HOST"],
            port=int(creds["POLARDB_PORT"]),
            user=creds["POLARDB_USER"],
            password=pwd,
            database=creds["POLARDB_DB"],
            charset="utf8mb4",
            connect_timeout=10,
            read_timeout=120,
        )
        logger.info("PolarDB connected")
        return _conn


def _query(sql: str, params=None) -> pd.DataFrame:
    conn = _get_conn()
    return pd.read_sql(sql, conn, params=params)


def _in_clause(codes: list[str]) -> tuple[str, list[str]]:
    """Build a parameterized IN clause: returns ('(%s,%s,%s)', [codes])."""
    placeholders = ",".join(["%s"] * len(codes))
    return f"({placeholders})", list(codes)


def _normalize_stock_df(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["stock_code"] = df.apply(
        lambda r: _from_polardb(r["code"], r.get("full_code", "")), axis=1
    )
    out["trade_date"] = pd.to_datetime(df["trading_day"])
    out["open"] = pd.to_numeric(df["open_price"], errors="coerce")
    out["high"] = pd.to_numeric(df["high_price"], errors="coerce")
    out["low"] = pd.to_numeric(df["low_price"], errors="coerce")
    out["close"] = pd.to_numeric(df["close_price"], errors="coerce")
    out["volume"] = pd.to_numeric(df["turnover_volume"], errors="coerce") * 100.0
    out["amount"] = pd.to_numeric(df["turnover_value"], errors="coerce")
    out["pct_change"] = pd.to_numeric(df.get("change_pct"), errors="coerce")
    return out[DAILY_COLUMNS].sort_values(["stock_code", "trade_date"])


@register
class PolarDBProvider(BaseProvider):
    name = "polardb"
    supported_asset_types = {"stock", "index"}

    def fetch_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        if adjust != "none":
            logger.warning("PolarDB returns unadjusted prices; adjust='%s' ignored", adjust)
        polardb_codes = [_to_polardb_code(c) for c in codes]
        all_dfs: list[pd.DataFrame] = []

        for i in range(0, len(polardb_codes), 500):
            chunk = polardb_codes[i : i + 500]
            in_sql, in_params = _in_clause(chunk)
            sql = (
                f"SELECT code, full_code, trading_day, "
                f"open_price, high_price, low_price, close_price, "
                f"turnover_volume, turnover_value, change_pct "
                f"FROM ads_stock_market_quotations_day "
                f"WHERE code IN {in_sql} "
                f"AND market_type IN ('sh','sz') "
                f"AND trading_day BETWEEN %s AND %s "
                f"ORDER BY trading_day"
            )
            params = in_params + [start_date, end_date]
            try:
                df = _query(sql, params)
                if df is not None and len(df) > 0:
                    all_dfs.append(df)
            except Exception as e:
                logger.error("PolarDB fetch chunk %d failed: %s", i // 500 + 1, e)

            if (i // 500 + 1) % 5 == 0:
                logger.info("PolarDB progress: %d/%d codes", min(i + 500, len(polardb_codes)), len(polardb_codes))

        if not all_dfs:
            return pd.DataFrame(columns=DAILY_COLUMNS)
        return _normalize_stock_df(pd.concat(all_dfs, ignore_index=True))

    def fetch_benchmark(
        self,
        name: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        secu = _BENCHMARK_CODES.get(name)
        if not secu:
            raise ValueError(f"Unknown benchmark '{name}' for polardb. Available: {list(_BENCHMARK_CODES)}")

        cols = (
            "secucode, trading_day, open_price, high_price, low_price, "
            "close_price, turnover_volume, turnover_value, change_pct"
        )
        frames: list[pd.DataFrame] = []
        for table in ("ads_index_market_quotations_day", "ads_index_market_quotations_day_new"):
            sql = (
                f"SELECT {cols} FROM {table} "
                f"WHERE secucode = %s AND trading_day BETWEEN %s AND %s "
                f"ORDER BY trading_day"
            )
            try:
                df = _query(sql, [secu, start_date, end_date])
                if df is not None and len(df) > 0:
                    frames.append(df)
            except Exception:
                continue

        if not frames:
            return pd.DataFrame(columns=["trade_date", "close", "daily_return"])

        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["trading_day"], keep="first")

        out = pd.DataFrame()
        out["trade_date"] = pd.to_datetime(merged["trading_day"])
        out["close"] = pd.to_numeric(merged["close_price"], errors="coerce")
        out = out.sort_values("trade_date")
        out["daily_return"] = out["close"].pct_change()
        return out[["trade_date", "close", "daily_return"]].copy()

    def list_instruments(
        self,
        asset_type: str,
        date: str | None = None,
    ) -> list[str]:
        if asset_type != "stock":
            raise ValueError(f"PolarDB list_instruments only supports 'stock', got '{asset_type}'")

        from datetime import datetime
        date = date or datetime.now().strftime("%Y-%m-%d")

        sql = (
            "SELECT DISTINCT code, full_code FROM ads_stock_market_quotations_day "
            "WHERE market_type IN ('sh','sz') AND trading_day = %s"
        )
        df = _query(sql, [date])
        if df is None or len(df) == 0:
            return []

        codes = []
        for _, row in df.iterrows():
            codes.append(_from_polardb(row["code"], row.get("full_code", "")))
        return sorted(codes)

    def list_universe(
        self,
        universe: str,
        date: str | None = None,
    ) -> list[str]:
        raise NotImplementedError(
            "PolarDB does not store index constituents. Use rqdatac or baostock."
        )
