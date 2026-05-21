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

# --- 1. Stocks: incremental update all cached ---
echo ""
echo "[1/5] Stocks — incremental (cached only)"
python -m adata fetch --source $SOURCE --category stocks --mode incremental || echo "WARN: stocks failed"

# --- 2. ETF: incremental update all cached ---
echo ""
echo "[2/5] ETF — incremental (cached only)"
python -m adata fetch --source $SOURCE --category etf --mode incremental || echo "WARN: ETF failed"

# --- 3. HK Stocks: incremental update all cached ---
echo ""
echo "[3/5] HK Stocks — incremental (cached only)"
python -m adata fetch --source $SOURCE --category hk --mode incremental || echo "WARN: HK stocks failed"

# --- 4. Benchmarks ---
echo ""
echo "[4/5] Benchmarks"
python -m adata fetch --source $SOURCE --benchmark hs300,csi500,csi1000,sz50,hsi,hscei,hstech || echo "WARN: benchmarks failed"

# --- 5. Status report ---
echo ""
echo "[5/5] Status report"
echo "=========================================="
echo "Update complete — $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
python -m adata status

echo ""
echo "Log saved to: $LOG_FILE"
