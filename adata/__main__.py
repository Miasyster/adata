"""CLI entry point — python -m adata."""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adata",
        description="Agent-Native financial data infrastructure",
    )
    sub = parser.add_subparsers(dest="command")

    # --- fetch ---
    fetch = sub.add_parser("fetch", help="Fetch market data")
    fetch.add_argument(
        "--source",
        default="rqdatac",
        help="Data provider (default: rqdatac)",
    )
    fetch.add_argument(
        "--category",
        default="stocks",
        help="Asset category: stocks, etf, index (default: stocks)",
    )
    fetch.add_argument(
        "--universe",
        default=None,
        help="Universe name: hs300, csi500, csi1000, csi2000, all_a",
    )
    fetch.add_argument(
        "--codes",
        default=None,
        help="Comma-separated instrument codes (e.g. sh.600519,sz.000001)",
    )
    fetch.add_argument(
        "--mode",
        default="incremental",
        choices=["incremental", "full"],
        help="Update mode (default: incremental)",
    )
    fetch.add_argument(
        "--start",
        default=None,
        help="Start date YYYY-MM-DD (default: 2015-01-01 for full mode)",
    )
    fetch.add_argument(
        "--end",
        default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    fetch.add_argument(
        "--benchmark",
        default=None,
        help="Comma-separated benchmark names: hs300,zz500,csi1000,sz50",
    )
    fetch.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Batch size per API call (default: 200)",
    )

    # --- status ---
    status = sub.add_parser("status", help="Show cache statistics")
    status.add_argument(
        "--category",
        default=None,
        help="Category to inspect (default: all)",
    )

    # --- mcp ---
    sub.add_parser("mcp", help="Start MCP server (stdio)")

    return parser


def _cmd_fetch(args: argparse.Namespace):
    from .config import get_data_dir
    from .providers import get_provider
    from .store import ParquetStore
    from .updater import DataUpdater

    provider = get_provider(args.source)
    store = ParquetStore(get_data_dir())
    updater = DataUpdater(provider, store)

    if args.benchmark:
        names = [n.strip() for n in args.benchmark.split(",")]
        result = updater.fetch_benchmarks(names, args.start, args.end)
        print(f"Benchmark update: {result}")
        return

    if args.universe == "all":
        asset_type = {"stocks": "stock", "etf": "etf", "index": "index"}.get(
            args.category, "stock"
        )
        codes = provider.list_instruments(asset_type)
        if not codes:
            print(f"No instruments found for {args.category}", file=sys.stderr)
            sys.exit(1)
        print(f"All {args.category}: {len(codes)} instruments")
        result = updater.fetch(
            codes=codes,
            start_date=args.start,
            end_date=args.end,
            mode=args.mode,
            category=args.category,
            batch_size=args.batch_size,
        )
    elif args.universe:
        result = updater.fetch_by_universe(
            universe=args.universe,
            start_date=args.start,
            end_date=args.end,
            mode=args.mode,
            category=args.category,
            batch_size=args.batch_size,
        )
    elif args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
        result = updater.fetch(
            codes=codes,
            start_date=args.start,
            end_date=args.end,
            mode=args.mode,
            category=args.category,
            batch_size=args.batch_size,
        )
    else:
        cached = store.list_cached(args.category)
        if not cached:
            print(
                "No cached data found. Use --universe or --codes to specify targets.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.mode == "full" and not args.start:
            print(
                "Full mode without --codes or --universe requires --start.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Updating {len(cached)} cached instruments...")
        result = updater.fetch(
            codes=cached,
            start_date=args.start,
            end_date=args.end,
            mode=args.mode,
            category=args.category,
            batch_size=args.batch_size,
        )

    print(f"Done: {result}")
    if result.errors:
        for err in result.errors:
            print(f"  ERROR: {err}", file=sys.stderr)


def _cmd_status(args: argparse.Namespace):
    from .config import get_data_dir
    from .store import ParquetStore

    store = ParquetStore(get_data_dir())
    data_dir = get_data_dir()
    print(f"Data directory: {data_dir}")

    categories = [args.category] if args.category else ["stocks", "etf", "index", "benchmark"]
    for cat in categories:
        cat_dir = data_dir / cat
        if not cat_dir.is_dir():
            continue
        s = store.stats(cat)
        if s["files"] == 0:
            continue
        print(f"\n  [{cat}]")
        print(f"    Files:      {s['files']}")
        print(f"    Date range: {s['date_range']}")
        print(f"    Total rows: {s['total_rows']:,}")


def _cmd_mcp():
    from .mcp_server import mcp
    mcp.run(transport="stdio")


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "fetch":
        _cmd_fetch(args)
    elif args.command == "status":
        _cmd_status(args)
    elif args.command == "mcp":
        _cmd_mcp()


if __name__ == "__main__":
    main()
