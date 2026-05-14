"""Provider registry."""

from __future__ import annotations

from .base import BaseProvider

_REGISTRY: dict[str, type[BaseProvider]] = {}


def register(cls: type[BaseProvider]) -> type[BaseProvider]:
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(name: str, **kwargs) -> BaseProvider:
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")
    return _REGISTRY[name](**kwargs)


def list_providers() -> list[str]:
    return sorted(_REGISTRY)


try:
    from . import rqdatac_provider  # noqa: E402, F401
except Exception:
    pass

try:
    from . import baostock_provider  # noqa: F401
except Exception:
    pass

try:
    from . import akshare_provider  # noqa: F401
except Exception:
    pass

try:
    from . import tushare_provider  # noqa: F401
except Exception:
    pass

try:
    from . import polardb_provider  # noqa: F401
except Exception:
    pass
