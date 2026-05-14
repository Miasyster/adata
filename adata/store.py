"""Parquet store — per-instrument file-based storage."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .schema import CodeNormalizer

logger = logging.getLogger(__name__)


class ParquetStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def _path(self, code: str, category: str) -> Path:
        d = self.data_dir / category
        d.mkdir(parents=True, exist_ok=True)
        name = CodeNormalizer.to_parquet_name(code)
        return d / f"{name}.parquet"

    def read(self, code: str, category: str = "stocks") -> pd.DataFrame | None:
        p = self._path(code, category)
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p)
            if "trade_date" in df.columns:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
            return df
        except Exception as e:
            logger.warning("Failed to read %s: %s", p, e)
            return None

    def write(self, code: str, df: pd.DataFrame, category: str = "stocks"):
        if df is None or len(df) == 0:
            return
        p = self._path(code, category)
        df.to_parquet(p, index=False)

    def merge_incremental(self, code: str, new_df: pd.DataFrame, category: str = "stocks"):
        if new_df is None or len(new_df) == 0:
            return
        existing = self.read(code, category)
        if existing is not None and len(existing) > 0:
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
        else:
            merged = new_df.sort_values("trade_date")
        self.write(code, merged, category)

    def last_date(self, code: str, category: str = "stocks") -> str | None:
        df = self.read(code, category)
        if df is None or len(df) == 0:
            return None
        return str(df["trade_date"].max().date())

    def list_cached(self, category: str = "stocks") -> list[str]:
        d = self.data_dir / category
        if not d.is_dir():
            return []
        return [
            CodeNormalizer.from_parquet_name(f.stem)
            for f in sorted(d.glob("*.parquet"))
        ]

    def stats(self, category: str = "stocks") -> dict:
        import pyarrow.parquet as pq

        d = self.data_dir / category
        if not d.is_dir():
            return {"files": 0, "codes": [], "date_range": None, "total_rows": 0}

        files = sorted(d.glob("*.parquet"))
        if not files:
            return {"files": 0, "codes": [], "date_range": None, "total_rows": 0}

        total_rows = 0
        date_min = None
        date_max = None

        for f in files:
            try:
                pf = pq.ParquetFile(f)
                total_rows += pf.metadata.num_rows
                if "trade_date" in pf.schema_arrow.names:
                    col = pf.read(columns=["trade_date"])["trade_date"]
                    if len(col) > 0:
                        lo = col.to_pandas().min()
                        hi = col.to_pandas().max()
                        lo = pd.Timestamp(lo)
                        hi = pd.Timestamp(hi)
                        if date_min is None or lo < date_min:
                            date_min = lo
                        if date_max is None or hi > date_max:
                            date_max = hi
            except Exception:
                continue

        return {
            "files": len(files),
            "date_range": (
                f"{date_min.date()} ~ {date_max.date()}" if date_min else None
            ),
            "total_rows": total_rows,
        }
