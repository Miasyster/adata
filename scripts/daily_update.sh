#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${ADATA_DIR:-$HOME/.adata}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_update_$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "adata daily update — $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

SOURCE="rqdatac"

# --- 1. Stocks: hs300 / csi500 / csi1000 / csi2000 ---
echo ""
echo "[1/7] Stocks — hs300"
python -m adata fetch --source $SOURCE --universe hs300 --category stocks --mode incremental || echo "WARN: hs300 failed"

echo ""
echo "[2/7] Stocks — csi500"
python -m adata fetch --source $SOURCE --universe csi500 --category stocks --mode incremental || echo "WARN: csi500 failed"

echo ""
echo "[3/7] Stocks — csi1000"
python -m adata fetch --source $SOURCE --universe csi1000 --category stocks --mode incremental || echo "WARN: csi1000 failed"

echo ""
echo "[4/7] Stocks — csi2000"
python -m adata fetch --source $SOURCE --universe csi2000 --category stocks --mode incremental || echo "WARN: csi2000 failed"

# --- 2. ETF: all ETF instruments ---
echo ""
echo "[5/7] ETF — all (rqdatac)"
python -m adata fetch --source $SOURCE --universe all --category etf --mode incremental || echo "WARN: ETF failed"

# --- 3. Benchmarks ---
echo ""
echo "[6/7] Benchmarks"
python -m adata fetch --source $SOURCE --benchmark hs300,csi500,csi1000,sz50 || echo "WARN: benchmarks failed"

# --- 4. Status report ---
echo ""
echo "[7/7] Status report"
echo "=========================================="
echo "Update complete — $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
python -m adata status

echo ""
echo "Log saved to: $LOG_FILE"
