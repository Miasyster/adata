"""DataUpdater — orchestrates provider + store for fetch operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .providers.base import BaseProvider
from .store import ParquetStore

logger = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    fetched: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.fetched + self.skipped + self.failed

    def __str__(self) -> str:
        parts = [f"fetched={self.fetched}"]
        if self.skipped:
            parts.append(f"skipped={self.skipped}")
        if self.failed:
            parts.append(f"failed={self.failed}")
        return f"UpdateResult({', '.join(parts)})"


class DataUpdater:
    def __init__(self, provider: BaseProvider, store: ParquetStore):
        self.provider = provider
        self.store = store

    def fetch(
        self,
        codes: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        mode: str = "incremental",
        category: str = "stocks",
        batch_size: int = 200,
    ) -> UpdateResult:
        end_date = end_date or date.today().isoformat()
        result = UpdateResult()

        if mode == "full":
            if not start_date:
                from .config import DEFAULT_START
                start_date = DEFAULT_START
            result = self._fetch_batch(codes, start_date, end_date, category, batch_size, overwrite=True)

        elif mode == "incremental":
            groups: dict[str, list[str]] = {}
            for code in codes:
                last = self.store.last_date(code, category)
                if last and last >= end_date:
                    result.skipped += 1
                    continue
                sd = _next_day(last) if last else (start_date or "2015-01-01")
                groups.setdefault(sd, []).append(code)

            for sd, batch_codes in sorted(groups.items()):
                r = self._fetch_batch(batch_codes, sd, end_date, category, batch_size, overwrite=False)
                result.fetched += r.fetched
                result.failed += r.failed
                result.errors.extend(r.errors)
        else:
            raise ValueError(f"Unknown mode '{mode}'. Use 'incremental' or 'full'.")

        return result

    def fetch_by_universe(
        self,
        universe: str,
        date: str | None = None,
        **kwargs,
    ) -> UpdateResult:
        codes = self.provider.list_universe(universe, date=date)
        if not codes:
            logger.warning("Universe '%s' returned no codes", universe)
            return UpdateResult()
        logger.info("Universe '%s': %d instruments", universe, len(codes))
        return self.fetch(codes=codes, **kwargs)

    def fetch_benchmarks(
        self,
        names: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> UpdateResult:
        from .config import DEFAULT_START

        start_date = start_date or DEFAULT_START
        end_date = end_date or date.today().isoformat()
        result = UpdateResult()

        for name in names:
            try:
                df = self.provider.fetch_benchmark(name, start_date, end_date)
                if df is not None and len(df) > 0:
                    bm_code = f"benchmark_{name}"
                    self.store.write(bm_code, df, category="benchmark")
                    result.fetched += 1
                    logger.info("Benchmark '%s': %d rows", name, len(df))
                else:
                    result.skipped += 1
            except Exception as e:
                result.failed += 1
                result.errors.append(f"benchmark:{name} — {e}")
                logger.error("Benchmark '%s' failed: %s", name, e)

        return result

    def _fetch_batch(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        category: str,
        batch_size: int,
        overwrite: bool,
    ) -> UpdateResult:
        result = UpdateResult()

        for i in range(0, len(codes), batch_size):
            chunk = codes[i : i + batch_size]
            logger.info(
                "Fetching batch %d/%d (%d codes) [%s → %s]",
                i // batch_size + 1,
                (len(codes) - 1) // batch_size + 1,
                len(chunk),
                start_date,
                end_date,
            )
            try:
                df = self.provider.fetch_daily(chunk, start_date, end_date)
            except Exception as e:
                result.failed += len(chunk)
                result.errors.append(f"batch {i//batch_size+1}: {e}")
                logger.error("Batch fetch failed: %s", e)
                continue

            if df is None or len(df) == 0:
                result.skipped += len(chunk)
                continue

            for code, group in df.groupby("stock_code"):
                if overwrite:
                    self.store.write(code, group, category)
                else:
                    self.store.merge_incremental(code, group, category)
                result.fetched += 1

            fetched_codes = set(df["stock_code"].unique())
            missed = [c for c in chunk if c not in fetched_codes]
            result.skipped += len(missed)

        return result


def _next_day(date_str: str) -> str:
    from datetime import timedelta
    d = date.fromisoformat(date_str) + timedelta(days=1)
    return d.isoformat()
