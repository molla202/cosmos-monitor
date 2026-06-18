#!/usr/bin/env bash
# Direct patch — bypasses pip cache, overwrites installed files in-place
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "  ${GREEN}✓ $*${NC}"; }
err() { echo -e "  ${RED}✗ $*${NC}"; exit 1; }
echo -e "${CYAN}▸ Patching cosmos-monitor in-place${NC}"

# Find installed location
PKG=$(python3.11 -c "import cosmos_monitor; import os; print(os.path.dirname(cosmos_monitor.__file__))" 2>/dev/null || \
      python3    -c "import cosmos_monitor; import os; print(os.path.dirname(cosmos_monitor.__file__))" 2>/dev/null || \
      echo "")

[[ -z "$PKG" ]] && err "cosmos-monitor not installed. Run install.sh first."
echo -e "${CYAN}▸ Found package at: $PKG${NC}"

BASE="https://raw.githubusercontent.com/Edsny1/cosmos-monitor/main/cosmos_monitor"

for f in dashboard.py chain.py cli.py fetcher.py __init__.py; do
    curl -sSL "$BASE/$f" -o "$PKG/$f"
    ok "Updated $f"
done

# Quick sanity check
python3.11 -c "import cosmos_monitor.dashboard" 2>/dev/null || \
python3    -c "import cosmos_monitor.dashboard" && ok "Import check passed"

echo
echo -e "${GREEN}Patch complete! Run: cosmos-monitor${NC}"
