#!/usr/bin/env bash
set -euo pipefail
GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "  ${GREEN}✓ $*${NC}"; }
err() { echo -e "  ${RED}✗ $*${NC}"; exit 1; }

echo -e "${CYAN}▸ Finding cosmos-monitor package${NC}"
PY=""
for p in python3.11 python3; do
    command -v "$p" >/dev/null 2>&1 && PY="$p" && break
done
[[ -z "$PY" ]] && err "Python not found"

PKG=$($PY -c "import cosmos_monitor,os; print(os.path.dirname(cosmos_monitor.__file__))" 2>/dev/null || echo "")
[[ -z "$PKG" ]] && err "cosmos-monitor not installed"
ok "Package: $PKG"

echo -e "${CYAN}▸ Downloading latest files${NC}"
BASE="https://raw.githubusercontent.com/Edsny1/cosmos-monitor/main/cosmos_monitor"
for f in dashboard.py fetcher.py chain.py cli.py __init__.py; do
    curl -fsSL "$BASE/$f" -o "$PKG/$f" && ok "$f"
done

echo -e "${CYAN}▸ Verifying${NC}"
$PY -c "import cosmos_monitor.dashboard, cosmos_monitor.fetcher" && ok "Import OK"
echo -e "\n${GREEN}Done! Run: cosmos-monitor${NC}\n"
