"""
Chain auto-detection — fully automatic, no hardcoded list needed.

Algorithm:
  1. Scan every ~/.xxx directory in $HOME
  2. If it contains config/config.toml  → treat as a Cosmos node home
  3. Read chain_id from config/genesis.json
  4. Read ports from config/config.toml + config/app.toml
  5. Guess binary name from the folder name
  6. Apply cosmetic overrides (nice name, denom, color) only for known chains
     — unknown chains still work, just with auto-generated metadata
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Cosmetic overrides for well-known chains ──────────────────────────────────
# Only used for display name / denom / color.
# Detection itself is fully automatic — this dict is NOT required.
_COSMETIC: dict[str, dict] = {
    "push_42101-1":        {"name": "Push Chain",          "denom": "PC",     "color": "cyan"},
    "celestia":            {"name": "Celestia",             "denom": "TIA",    "color": "bright_magenta"},
    "mocha-4":             {"name": "Celestia Mocha",       "denom": "TIA",    "color": "magenta"},
    "lumera-testnet-2":    {"name": "Lumera",               "denom": "LUME",   "color": "bright_green"},
    "lumera-1":            {"name": "Lumera",               "denom": "LUME",   "color": "bright_green"},
    "osmosis-1":           {"name": "Osmosis",              "denom": "OSMO",   "color": "bright_yellow"},
    "cosmoshub-4":         {"name": "Cosmos Hub",           "denom": "ATOM",   "color": "bright_blue"},
    "atomone-1":           {"name": "AtomOne",              "denom": "ATONE",  "color": "blue"},
    "axelar-dojo-1":       {"name": "Axelar",               "denom": "AXL",    "color": "bright_red"},
    "stride-1":            {"name": "Stride",               "denom": "STRD",   "color": "bright_cyan"},
    "pirin-1":             {"name": "Nolus",                "denom": "NLS",    "color": "yellow"},
    "cardchain":           {"name": "Cardchain",            "denom": "ubpf",   "color": "bright_yellow"},
    "safrochain":          {"name": "Safrochain",           "denom": "SAFRO",  "color": "bright_green"},
    "arkh":                {"name": "Arkh",                 "denom": "arkh",   "color": "yellow"},
    "bitbadges-1":         {"name": "BitBadges",            "denom": "badge",  "color": "bright_magenta"},
    "drosera-1":           {"name": "Drosera",              "denom": "DRO",    "color": "green"},
    "evmos_9001-2":        {"name": "Evmos",                "denom": "EVMOS",  "color": "bright_red"},
    "injective-1":         {"name": "Injective",            "denom": "INJ",    "color": "blue"},
    "juno-1":              {"name": "Juno",                 "denom": "JUNO",   "color": "bright_cyan"},
    "stargaze-1":          {"name": "Stargaze",             "denom": "STARS",  "color": "magenta"},
    "kaiyo-1":             {"name": "Kujira",               "denom": "KUJI",   "color": "bright_red"},
    "cataclysm-1":         {"name": "Nibiru",               "denom": "NIBI",   "color": "bright_yellow"},
    "mantra-1":            {"name": "Mantra",               "denom": "OM",     "color": "yellow"},
    "dymension_1100-1":    {"name": "Dymension",            "denom": "DYM",    "color": "bright_blue"},
    "zetachain_7000-1":    {"name": "ZetaChain",            "denom": "ZETA",   "color": "green"},
    "lava-testnet-2":      {"name": "Lava Network",         "denom": "LAVA",   "color": "bright_red"},
    "bbn-1":               {"name": "Babylon",              "denom": "BBN",    "color": "bright_yellow"},
    "union-testnet-8":     {"name": "Union",                "denom": "UNO",    "color": "bright_white"},
    "crossfi-evm-testnet-1":{"name": "Crossfi",             "denom": "MPX",    "color": "cyan"},
}

# Color cycle for unknown chains (assigned by index)
_COLOR_CYCLE = [
    "bright_green", "bright_cyan", "bright_yellow", "bright_magenta",
    "bright_red", "bright_blue", "cyan", "yellow", "green", "magenta",
    "blue", "red",
]


@dataclass
class PortConfig:
    rpc:   int = 26657
    p2p:   int = 26656
    grpc:  int = 9090
    rest:  int = 1317
    pprof: int = 6060


@dataclass
class ChainConfig:
    home_dir: str
    chain_id: str
    name:     str
    denom:    str
    binary:   str
    color:    str
    ports:    PortConfig = field(default_factory=PortConfig)
    moniker:  str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _has_valid_config(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "config", "config.toml"))


def _chain_id_from_genesis(home_dir: str) -> str:
    genesis = os.path.join(home_dir, "config", "genesis.json")
    if not os.path.exists(genesis):
        return ""
    try:
        with open(genesis, encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("chain_id") or
            data.get("genesis", {}).get("chain_id") or
            ""
        )
    except Exception:
        return ""


def _moniker_from_config(home_dir: str) -> str:
    config_toml = os.path.join(home_dir, "config", "config.toml")
    try:
        with open(config_toml, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r'moniker\s*=\s*"([^"]+)"', content)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _parse_ports(home_dir: str) -> PortConfig:
    ports = PortConfig()
    config_toml = os.path.join(home_dir, "config", "config.toml")
    app_toml    = os.path.join(home_dir, "config", "app.toml")

    if os.path.exists(config_toml):
        try:
            text = open(config_toml, encoding="utf-8").read()
            m = re.search(r'\[rpc\].*?laddr\s*=\s*"tcp://[^:]+:(\d+)"',  text, re.DOTALL)
            if m: ports.rpc  = int(m.group(1))
            m = re.search(r'\[p2p\].*?laddr\s*=\s*"tcp://[^:]+:(\d+)"',  text, re.DOTALL)
            if m: ports.p2p  = int(m.group(1))
            m = re.search(r'pprof_laddr\s*=\s*"[^:]+:(\d+)"', text)
            if m: ports.pprof = int(m.group(1))
        except Exception:
            pass

    if os.path.exists(app_toml):
        try:
            text = open(app_toml, encoding="utf-8").read()
            m = re.search(r'\[grpc\].*?address\s*=\s*"[^:]+:(\d+)"',      text, re.DOTALL)
            if m: ports.grpc = int(m.group(1))
            m = re.search(r'\[api\].*?address\s*=\s*"tcp://[^:]+:(\d+)"', text, re.DOTALL)
            if m: ports.rest = int(m.group(1))
        except Exception:
            pass

    return ports


def _guess_binary(folder_name: str, chain_id: str) -> str:
    """
    Try to find the actual running binary for this chain.
    Falls back to a reasonable guess from the folder/chain name.
    """
    # 1. Check if a binary matching the folder name is in PATH
    base = folder_name.lstrip(".")          # e.g. "pchain", "celestia-app"
    candidates = [
        base,                               # pchain
        base + "d",                         # pchaind
        base.replace("-", "") + "d",        # celestiaappd
        base.split("-")[0] + "d",           # celestiad
        base.split("-")[0],                 # celestia
        chain_id.split("_")[0],             # push  (from push_42101-1)
        chain_id.split("-")[0],             # lumera (from lumera-testnet-2)
        chain_id.split("-")[0] + "d",       # lumerad
    ]
    for c in candidates:
        if c and _binary_exists(c):
            return c

    # 2. Scan running processes for something that looks like this chain
    proc = _find_process_binary(chain_id, base)
    if proc:
        return proc

    # 3. Best-effort guess (may not exist, but shows the right name)
    return base + "d" if not base.endswith("d") else base


def _binary_exists(name: str) -> bool:
    """Check whether a binary is in PATH."""
    try:
        result = subprocess.run(
            ["which", name],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def _find_process_binary(chain_id: str, folder_base: str) -> str:
    """
    Look through /proc to find a running binary for this chain.
    Returns the binary name if found, empty string otherwise.
    """
    keywords = {
        chain_id.split("_")[0],
        chain_id.split("-")[0],
        folder_base.split("-")[0],
    } - {""}
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_text().split("\x00")
                if not cmdline:
                    continue
                binary = os.path.basename(cmdline[0])
                for kw in keywords:
                    if kw and len(kw) > 2 and kw.lower() in binary.lower():
                        return binary
            except Exception:
                continue
    except Exception:
        pass
    return ""


def _auto_name(folder_name: str, chain_id: str) -> str:
    """Generate a human-readable name when not in _COSMETIC."""
    base = folder_name.lstrip(".")
    # Prefer the chain_id prefix: "lumera-testnet-2" → "Lumera"
    prefix = chain_id.split("_")[0].split("-")[0]
    if prefix and len(prefix) > 2:
        return prefix.replace("-", " ").title()
    return base.replace("-", " ").replace("_", " ").title()


def _auto_denom(chain_id: str, folder_name: str) -> str:
    """Guess a denom token name."""
    prefix = chain_id.split("_")[0].split("-")[0]
    return prefix.upper() if prefix and len(prefix) >= 2 else "TOKEN"


# ── Main detection function ───────────────────────────────────────────────────

def detect_chains(
    home_base: str = None,
    extra_homes: list[str] = None,
) -> list[ChainConfig]:
    """
    Fully automatic chain detection.

    Scans all dot-directories under $HOME for Cosmos node configs.
    No hardcoded chain list required.
    """
    base       = home_base or str(Path.home())
    candidates = list(extra_homes or [])

    # Auto-scan: every hidden directory that has config/config.toml
    try:
        for entry in sorted(os.scandir(base), key=lambda e: e.name):
            if not entry.name.startswith("."):
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            # Skip non-node dot-dirs
            skip = {".ssh", ".gnupg", ".cache", ".config", ".docker",
                    ".cargo", ".npm", ".nvm", ".bun", ".rustup",
                    ".local", ".foundry", ".git", ".vscode"}
            if entry.name in skip:
                continue
            if _has_valid_config(entry.path):
                if entry.path not in candidates:
                    candidates.append(entry.path)
    except PermissionError:
        pass

    results: list[ChainConfig] = []
    color_idx = 0

    for home_dir in candidates:
        home_dir = os.path.expanduser(str(home_dir))
        if not _has_valid_config(home_dir):
            continue

        folder   = os.path.basename(home_dir)
        chain_id = _chain_id_from_genesis(home_dir) or folder.lstrip(".")

        # Cosmetic override by chain_id (most stable identifier)
        cosmetic = _COSMETIC.get(chain_id, {})

        # Also try partial match for chain_ids like "push_42101-1" → key "push_42101-1"
        if not cosmetic:
            for key, val in _COSMETIC.items():
                if chain_id.startswith(key) or key.startswith(chain_id.split("-")[0]):
                    cosmetic = val
                    break

        name   = cosmetic.get("name")  or _auto_name(folder, chain_id)
        denom  = cosmetic.get("denom") or _auto_denom(chain_id, folder)
        color  = cosmetic.get("color") or _COLOR_CYCLE[color_idx % len(_COLOR_CYCLE)]
        binary = _guess_binary(folder, chain_id)

        ports   = _parse_ports(home_dir)
        moniker = _moniker_from_config(home_dir)

        results.append(ChainConfig(
            home_dir=home_dir,
            chain_id=chain_id,
            name=name,
            denom=denom,
            binary=binary,
            color=color,
            ports=ports,
            moniker=moniker,
        ))
        color_idx += 1

    return results
