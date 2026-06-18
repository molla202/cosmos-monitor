#!/usr/bin/env bash
# cosmos-monitor installer
# Usage: bash install.sh
#        bash install.sh --dev   (install from current directory, editable)
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'
BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

status() { echo -e "${CYAN}▸ $*${NC}"; }
ok()     { echo -e "  ${GREEN}✓ $*${NC}"; }
warn()   { echo -e "  ${YELLOW}⚠ $*${NC}"; }
err()    { echo -e "  ${RED}✗ $*${NC}"; exit 1; }
step()   { echo -e "  ${DIM}→ $*${NC}"; }

DEV_MODE="no"
[[ "${1:-}" == "--dev" ]] && DEV_MODE="yes"

echo
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      cosmos-monitor  installer           ║${NC}"
echo -e "${BOLD}║      Oshvank Validator Dashboard         ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo

# ── Python: find 3.11+ regardless of system default ───────────────
# Ubuntu 22.04 ships python3=3.10 by default even after python3.11 install
status "Checking Python"
PY_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        _VER=$("$candidate" --version 2>&1 | awk '{print $2}')
        _MAJ=$(echo "$_VER" | cut -d. -f1)
        _MIN=$(echo "$_VER" | cut -d. -f2)
        if [[ "$_MAJ" -ge 3 && "$_MIN" -ge 11 ]]; then
            PY_BIN="$candidate"
            ok "Found $candidate ($_VER)"
            break
        fi
    fi
done

if [[ -z "$PY_BIN" ]]; then
    FOUND_VER=$(python3 --version 2>&1 | awk '{print $2}' || echo "not found")
    err "Python 3.11+ required (found: $FOUND_VER)
  Install: sudo apt install python3.11
  Then run this installer again."
fi

# ── pip ───────────────────────────────────────────────────────────
status "Checking pip"
if ! "$PY_BIN" -m pip --version >/dev/null 2>&1; then
    warn "pip not found for $PY_BIN, attempting install"
    "$PY_BIN" -m ensurepip --upgrade 2>/dev/null || \
        sudo apt-get install -y python3.11-pip 2>/dev/null || \
        sudo apt-get install -y python3-pip 2>/dev/null || \
        err "Could not install pip. Run: sudo apt install python3.11-pip"
fi
ok "pip available ($PY_BIN -m pip)"

# ── Upgrade pip + setuptools (critical on Ubuntu 22.04) ───────────
status "Upgrading pip and setuptools"
"$PY_BIN" -m pip install --break-system-packages --upgrade \
    pip setuptools wheel 2>/dev/null || \
"$PY_BIN" -m pip install --upgrade \
    pip setuptools wheel
ok "pip + setuptools upgraded"

# ── Install cosmos-monitor ────────────────────────────────────────
status "Installing cosmos-monitor"

REPO_URL="https://github.com/Edsny1/cosmos-monitor.git"

if [[ "$DEV_MODE" == "yes" ]]; then
    step "Dev mode: editable install from current directory"
    "$PY_BIN" -m pip install --break-system-packages -e . 2>/dev/null || \
    "$PY_BIN" -m pip install -e .
else
    step "Installing from GitHub: $REPO_URL"
    "$PY_BIN" -m pip install --break-system-packages \
        "git+${REPO_URL}" 2>/dev/null || \
    "$PY_BIN" -m pip install \
        "git+${REPO_URL}"
fi

ok "cosmos-monitor installed"

# ── PATH ──────────────────────────────────────────────────────────
status "Checking PATH"

PY_USER_BASE=$("$PY_BIN" -m site --user-base 2>/dev/null || echo "$HOME/.local")
PY_SCRIPTS="$PY_USER_BASE/bin"

INSTALLED_AT=""
for CHECK_DIR in "$PY_SCRIPTS" "/usr/local/bin" "/usr/bin" "$HOME/.local/bin"; do
    if [[ -f "$CHECK_DIR/cosmos-monitor" ]]; then
        INSTALLED_AT="$CHECK_DIR"
        break
    fi
done
INSTALLED_AT="${INSTALLED_AT:-$PY_SCRIPTS}"

if ! echo "$PATH" | grep -q "$INSTALLED_AT"; then
    warn "$INSTALLED_AT not in PATH — adding automatically"
    SHELL_RC="$HOME/.bashrc"
    [[ "${SHELL##*/}" == "zsh" ]] && SHELL_RC="$HOME/.zshrc"
    {
        echo ""
        echo "# cosmos-monitor"
        echo "export PATH=\"$INSTALLED_AT:\$PATH\""
    } >> "$SHELL_RC"
    export PATH="$INSTALLED_AT:$PATH"
    ok "Added $INSTALLED_AT to PATH in $SHELL_RC"
else
    ok "PATH already configured"
fi

# ── Assets: logo ─────────────────────────────────────────────────
status "Checking assets"
LOGO_SRC="$("$PY_BIN" -c "
import cosmos_monitor, os
print(os.path.join(os.path.dirname(cosmos_monitor.__file__), '..', 'assets', 'logo.ansi'))
" 2>/dev/null || echo "")"

if [[ -f "$LOGO_SRC" ]]; then
    ok "ANSI logo found"
else
    warn "Logo asset not found — dashboard will show text fallback"
fi

# ── Detect chains ─────────────────────────────────────────────────
status "Detecting Cosmos chains on this server"
cosmos-monitor --list 2>/dev/null || \
    "$PY_BIN" -m cosmos_monitor.cli --list 2>/dev/null || \
    warn "No chains detected yet. Run 'cosmos-monitor --list' after installing a node."

echo
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        Installation Complete!  ✓         ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo
echo "  Quick start:"
echo "    cosmos-monitor                      # auto-detect all chains"
echo "    cosmos-monitor --home ~/.pchain     # specific chain"
echo "    cosmos-monitor --list               # show detected chains"
echo "    cosmos-monitor --help               # all options"
echo
echo -e "  ${DIM}If 'cosmos-monitor' is not found, run: source ~/.bashrc${NC}"
echo
