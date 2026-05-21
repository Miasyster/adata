"""Standard schema definitions and code normalization."""

from __future__ import annotations

import re

DAILY_COLUMNS = [
    "trade_date",
    "stock_code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_change",
]

BENCHMARK_COLUMNS = ["trade_date", "close", "daily_return"]

_RQ_SUFFIX = {"sh": "XSHG", "sz": "XSHE", "hk": "XHKG"}
_RQ_SUFFIX_REV = {v: k for k, v in _RQ_SUFFIX.items()}

_NORMALIZE_RE = re.compile(
    r"^(?:(?P<pfx>[A-Za-z]{2})[\._]?(?P<num>\d{5,6}))"
    r"|(?:(?P<num2>\d{5,6})[\._](?P<sfx>[A-Za-z]{2,4}))$"
)


class CodeNormalizer:
    """Multi-format → standard format sh.600519."""

    @staticmethod
    def normalize(raw: str) -> str:
        raw = raw.strip()
        m = _NORMALIZE_RE.match(raw)
        if not m:
            return raw.lower()

        if m.group("pfx") and m.group("num"):
            pfx = m.group("pfx").lower()
            num = m.group("num")
            if pfx in ("sh", "sz", "hk"):
                return f"{pfx}.{num}"
            if pfx in _RQ_SUFFIX_REV:
                return f"{_RQ_SUFFIX_REV[pfx]}.{num}"
            return f"{pfx}.{num}"

        num = m.group("num2")
        sfx = m.group("sfx").upper()
        if sfx in ("SH", "SZ", "HK"):
            return f"{sfx.lower()}.{num}"
        if sfx in _RQ_SUFFIX_REV:
            return f"{_RQ_SUFFIX_REV[sfx]}.{num}"
        return f"{sfx.lower()}.{num}"

    @staticmethod
    def to_rqdatac(code: str) -> str:
        code = CodeNormalizer.normalize(code)
        parts = code.split(".")
        if len(parts) == 2 and parts[0] in _RQ_SUFFIX:
            return f"{parts[1]}.{_RQ_SUFFIX[parts[0]]}"
        return code

    @staticmethod
    def to_baostock(code: str) -> str:
        return CodeNormalizer.normalize(code)

    @staticmethod
    def to_parquet_name(code: str) -> str:
        return CodeNormalizer.normalize(code).replace(".", "_")

    @staticmethod
    def from_parquet_name(name: str) -> str:
        name = name.removesuffix(".parquet")
        parts = name.split("_", 1)
        if len(parts) == 2 and parts[0] in ("sh", "sz", "hk"):
            return f"{parts[0]}.{parts[1]}"
        return name

    @staticmethod
    def from_rqdatac(rq_code: str) -> str:
        parts = rq_code.split(".")
        if len(parts) == 2 and parts[1] in _RQ_SUFFIX_REV:
            return f"{_RQ_SUFFIX_REV[parts[1]]}.{parts[0]}"
        return rq_code
