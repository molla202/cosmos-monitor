"""Fetch live node data — RPC, REST, process info, logs."""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from .chain import ChainConfig


@dataclass
class ValidatorInfo:
    moniker:       str  = ""
    operator_addr: str  = ""
    status:        str  = "UNKNOWN"
    voting_power:  str  = "0"
    commission:    str  = "0%"
    comm_rewards:  str  = "0"
    outstanding:   str  = "0"
    jailed:        bool = False


@dataclass
class NodeStatus:
    running:       bool  = False
    pid:           int   = 0
    uptime_sec:    int   = 0
    mem_pct:       float = 0.0
    disk_pct:      float = 0.0
    version:       str   = ""
    latest_block:  int   = 0
    network_block: int   = 0
    syncing:       bool  = True
    sync_pct:      float = 0.0
    peers:         int   = 0
    node_id:       str   = ""
    network:       str   = ""
    chain_id:      str   = ""
    moniker:       str   = ""
    latency_ms:    int   = 0
    validator:     ValidatorInfo = field(default_factory=ValidatorInfo)
    validators:    list  = field(default_factory=list)
    log_lines:     list  = field(default_factory=list)
    error:         str   = ""


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 4) -> Optional[dict]:
    try:
        t0  = time.monotonic()
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            lat  = int((time.monotonic() - t0) * 1000)
            data = json.loads(resp.read().decode())
            if isinstance(data, dict):
                data["_lat"] = lat
            return data
    except Exception:
        return None


# ── Process info ──────────────────────────────────────────────────────────────

def _proc(binary: str):
    """Returns (running, pid, uptime_sec, mem_pct)."""
    try:
        r = subprocess.run(["pgrep", "-f", binary], capture_output=True, text=True)
        pids = [p for p in r.stdout.strip().split() if p.isdigit()]
        if not pids:
            return False, 0, 0, 0.0
        pid = int(pids[0])

        uptime = 0
        try:
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().split()
            starttime = int(fields[21])
            with open("/proc/uptime") as f:
                sys_up = float(f.read().split()[0])
            
            hz = 100
            try:
                if hasattr(os, 'sysconf'):
                    hz = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", 100))
            except Exception:
                pass
            uptime = max(0, int(sys_up - starttime / hz))
        except Exception:
            pass

        mem_pct = 0.0
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        break
            with open("/proc/meminfo") as f:
                total_kb = int(f.readline().split()[1])
            mem_pct = round(rss_kb / total_kb * 100, 1)
        except Exception:
            pass

        return True, pid, uptime, mem_pct
    except Exception:
        return False, 0, 0, 0.0


def _disk(path: str) -> float:
    try:
        st = os.statvfs(path)
        used  = (st.f_blocks - st.f_bfree) * st.f_frsize
        total = st.f_blocks * st.f_frsize
        return round(used / total * 100, 1) if total else 0.0
    except Exception:
        return 0.0


# ── Log reading ───────────────────────────────────────────────────────────────

def _read_logs(home_dir: str, pid: int = 0, binary: str = "", n: int = 30) -> list[str]:
    candidates = [
        os.path.join(home_dir, "logs", "node.log"),
        os.path.join(home_dir, "logs", f"{binary}.log") if binary else "",
        os.path.join(home_dir, "log",  "node.log"),
        os.path.join(home_dir, "logs", "app.log"),
        "/var/log/cosmovisor.log",
    ]
    # Check physical files first
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 16384))
                    raw = f.read().decode("utf-8", errors="replace").splitlines()
                return [l for l in raw if l.strip()][-n:]
            except Exception:
                pass

    # Try to find exactly which systemd service is running this PID
    unit = ""
    if pid > 0:
        try:
            with open(f"/proc/{pid}/cgroup") as f:
                for line in f:
                    if ".service" in line:
                        unit = line.strip().split("/")[-1]
                        break
        except Exception:
            pass

    if unit:
        try:
            r = subprocess.run(
                ["journalctl", "-u", unit, "-n", str(n), "--no-pager", "-q"],
                capture_output=True, text=True, timeout=3
            )
            lines = [l for l in r.stdout.splitlines() if l.strip()]
            if lines:
                return lines
        except Exception:
            pass

    # Fallback to syslog identifier (binary name)
    if binary:
        try:
            r = subprocess.run(
                ["journalctl", "-t", binary, "-n", str(n), "--no-pager", "-q"],
                capture_output=True, text=True, timeout=3
            )
            lines = [l for l in r.stdout.splitlines() if l.strip()]
            if lines:
                return lines
        except Exception:
            pass

    return []


# ── Validator data from REST ──────────────────────────────────────────────────

def _fmt_tokens(tokens: str) -> str:
    try:
        t = int(tokens)
        if t >= 1_000_000_000: return f"{t/1_000_000_000:.2f}B"
        if t >= 1_000_000:     return f"{t/1_000_000:.2f}M"
        if t >= 1_000:         return f"{t/1_000:.2f}K"
        return str(t)
    except Exception:
        return tokens


def _fmt_reward(amount_str: str, denom: str) -> str:
    """Parse reward amount from REST response."""
    try:
        # amount_str may be like "1234567.000000000000000000"
        val = float(amount_str)
        # Most cosmos chains use 6 decimal places (uatom → ATOM)
        # but some use 18. Try to detect.
        if val > 1_000_000:
            val = val / 1_000_000
        return f"{val:,.2f}"
    except Exception:
        return "0"


def _get_validators(rest: str, denom: str, moniker: str) -> tuple[list, ValidatorInfo]:
    my_val = ValidatorInfo()
    vals   = []

    # Fetch all validators (no bond status filter, max 3000 limit)
    data = _get(
        f"{rest}/cosmos/staking/v1beta1/validators"
        f"?pagination.limit=3000",
        timeout=5
    )
    if not data:
        return vals, my_val

    for v in data.get("validators", []):
        desc    = v.get("description", {})
        name    = desc.get("moniker", "unknown")
        tokens  = v.get("tokens", "0")
        jailed  = v.get("jailed", False)
        status  = v.get("status", "")
        op_addr = v.get("operator_address", "")

        # Commission
        try:
            rate = float(v.get("commission", {})
                          .get("commission_rates", {})
                          .get("rate", "0"))
            comm_str = f"{rate*100:.0f}%"
        except Exception:
            comm_str = "—"

        status_short = {
            "BOND_STATUS_BONDED":    "BONDED",
            "BOND_STATUS_UNBONDING": "UNBONDING",
            "BOND_STATUS_UNBONDED":  "UNBONDED",
        }.get(status, status.replace("BOND_STATUS_", "") if status else "UNKNOWN")

        entry = {
            "moniker":      name,
            "status":       status_short,
            "tokens":       _fmt_tokens(tokens),
            "commission":   comm_str,
            "operator":     op_addr,
            "jailed":       jailed,
            "comm_rewards": "—",
            "outstanding":  "—",
        }
        vals.append(entry)

        # Match our validator by moniker
        if name == moniker or (moniker and moniker.lower() in name.lower()):
            my_val.moniker       = name
            my_val.operator_addr = op_addr
            my_val.status        = status_short
            my_val.voting_power  = _fmt_tokens(tokens)
            my_val.commission    = comm_str
            my_val.jailed        = jailed

    # Sort: bonded first, then by tokens desc
    vals.sort(key=lambda x: (
        0 if x["status"] == "BONDED" else 1,
        x["moniker"]
    ))

    # Fetch rewards for our validator if found
    if my_val.operator_addr:
        _fetch_rewards(rest, my_val, denom)

    return vals, my_val


def _fetch_rewards(rest: str, my_val: ValidatorInfo, denom: str):
    """Fetch commission rewards and outstanding rewards."""
    op = my_val.operator_addr

    # Commission rewards
    cr = _get(f"{rest}/cosmos/distribution/v1beta1/validators/{op}/commission", timeout=4)
    if cr:
        commissions = (cr.get("commission", {})
                         .get("commission", []))
        for item in commissions:
            if denom.lower() in item.get("denom", "").lower() or \
               item.get("denom", "").startswith("u"):
                my_val.comm_rewards = _fmt_reward(item.get("amount", "0"), denom)
                break
        if not commissions and cr.get("commission"):
            # Some chains return differently
            try:
                amt = cr["commission"].get("amount", "0")
                if isinstance(amt, list) and amt:
                    my_val.comm_rewards = _fmt_reward(amt[0].get("amount","0"), denom)
            except Exception:
                pass

    # Outstanding rewards
    ow = _get(f"{rest}/cosmos/distribution/v1beta1/validators/{op}/outstanding_rewards", timeout=4)
    if ow:
        rewards = (ow.get("rewards", {})
                     .get("rewards", []))
        for item in rewards:
            if denom.lower() in item.get("denom", "").lower() or \
               item.get("denom", "").startswith("u"):
                my_val.outstanding = _fmt_reward(item.get("amount", "0"), denom)
                break


# ── Main fetch function ───────────────────────────────────────────────────────

def fetch_node_status(cfg: ChainConfig) -> NodeStatus:
    s    = NodeStatus()
    rpc  = f"http://127.0.0.1:{cfg.ports.rpc}"
    rest = f"http://127.0.0.1:{cfg.ports.rest}"

    # Process
    running, pid, uptime, mem = _proc(cfg.binary)
    s.running    = running
    s.pid        = pid
    s.uptime_sec = uptime
    s.mem_pct    = mem
    s.disk_pct   = _disk(cfg.home_dir)

    if not running:
        s.error    = f"{cfg.binary} not running"
        s.log_lines = _read_logs(cfg.home_dir, 0, cfg.binary)
        return s

    # RPC /status
    rs = _get(f"{rpc}/status")
    if rs:
        s.latency_ms = rs.get("_lat", 0)
        r = rs.get("result", rs)
        ni = r.get("node_info", {})
        sy = r.get("sync_info", {})

        s.node_id  = ni.get("id", "")
        s.network  = ni.get("network", cfg.chain_id)
        s.chain_id = ni.get("network", cfg.chain_id)
        s.moniker  = ni.get("moniker", cfg.moniker)
        s.version  = (ni.get("version", "") or
                      r.get("application_version", {}).get("version", ""))
        try:
            s.latest_block = int(sy.get("latest_block_height", 0))
        except Exception:
            pass
        s.syncing = sy.get("catching_up", True)
        s.sync_pct = 0.0 if s.syncing else 100.0

    # RPC /net_info
    ni2 = _get(f"{rpc}/net_info")
    if ni2:
        try:
            s.peers = int(ni2.get("result", ni2).get("n_peers", 0))
        except Exception:
            pass

    # REST validators + my validator
    s.validators, s.validator = _get_validators(
        rest, cfg.denom, s.moniker or cfg.moniker
    )

    # Logs
    s.log_lines = _read_logs(cfg.home_dir, s.pid, cfg.binary)

    return s
