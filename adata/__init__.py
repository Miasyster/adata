"""adata - Agent-Native financial data infrastructure."""

__version__ = "0.1.0"

from .client import DataClient
from .config import get_data_dir
from .store import ParquetStore
from .updater import DataUpdater

__all__ = ["DataClient", "get_data_dir", "ParquetStore", "DataUpdater", "__version__"]
