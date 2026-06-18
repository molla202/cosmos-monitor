"""cosmos-monitor — Textual TUI dashboard (textual 8.x compatible)."""

import asyncio
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import (
    Footer, Static, TabbedContent, TabPane,
    DataTable, RichLog,
)
from rich.markup import escape

from .chain import ChainConfig
from .fetcher import NodeStatus, fetch_node_status


def _fmt_uptime(sec: int) -> str:
    sec = max(0, sec)
    if sec < 60:    return f"{sec}s"
    if sec < 3600:  return f"{sec//60}m"
    if sec < 86400: return f"{sec//3600}h {(sec % 3600)//60}m"
    return f"{sec//86400}d {(sec % 86400)//3600}h"


def _bar(pct: float, w: int = 40) -> str:
    n = int(w * min(pct, 100) / 100)
    return "█" * n + "░" * (w - n)


def _sc(status: str) -> str:
    return {"BONDED": "bright_green", "UNBONDING": "yellow",
            "UNBONDED": "red"}.get(status, "dim")


def _tab_id(cfg: ChainConfig) -> str:
    return cfg.chain_id.replace("_", "-").replace(".", "-")


# ── PANELS ────────────────────────────────────────────────────────────────────

class NodePanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg = cfg
        self._d = NodeStatus()

    def update_data(self, d: NodeStatus):
        self._d = d
        self.refresh()

    def render(self):
        d = self._d
        ok = "[bright_green]✓[/]"
        no = "[red]✗[/]"
        
        proc = f"{ok} Running (pid {d.pid})" if d.running else f"{no} Not running"
        rpc  = f"{ok} Listening" if d.running else f"{no} Down"
        
        return (
            f"[bold]NODE STATUS[/]\n"
            f" {proc}\n"
            f" RPC: {rpc}\n"
            f" Uptime: {_fmt_uptime(d.uptime_sec)}\n"
            f" Memory: {d.mem_pct:.2f}%\n"
            f" Disk: {d.disk_pct:.2f}%\n"
            f" Version: {d.version or '—'}"
        )


class ChainPanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg = cfg
        self._d = NodeStatus()

    def update_data(self, d: NodeStatus):
        self._d = d
        self.refresh()

    def render(self):
        d = self._d
        sync = "In Sync" if not d.syncing else "Syncing"
        sc   = "bright_green" if not d.syncing else "yellow"
        
        return (
            f"[bold]CHAIN STATUS[/]\n\n"
            f" [{sc}]■ {sync}[/] [{sc}]{_bar(d.sync_pct, 40)}[/] {d.sync_pct:.2f}% | {d.latest_block:,} blocks"
        )


class NetworkPanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg = cfg
        self._d = NodeStatus()

    def update_data(self, d: NodeStatus):
        self._d = d
        self.refresh()

    def render(self):
        d = self._d
        nid = d.node_id or "—"
        return (
            f"[bold]NETWORK STATUS[/]\n"
            f" Connected to [bright_green]{d.peers}[/] peers (Node ID):\n"
            f"  [dim]{nid}[/]\n"
            f" Latency: {d.latency_ms}ms\n"
            f" Chain: {d.chain_id or self._cfg.chain_id}\n"
            f" Name: {d.moniker or self._cfg.moniker or '—'}\n"
            f" Ports: RPC:{self._cfg.ports.rpc} P2P:{self._cfg.ports.p2p} REST:{self._cfg.ports.rest}"
        )


class MyValPanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg = cfg
        self._d = NodeStatus()

    def update_data(self, d: NodeStatus):
        self._d = d
        self.refresh()

    def render(self):
        d = self._d
        v = d.validator
        sc = _sc(v.status)
        jail = "  [bold red]JAILED[/]" if v.jailed else ""
        
        def rcolor(val: str) -> str:
            try:
                return "bright_yellow" if float(val.replace(",","")) > 0 else "white"
            except Exception:
                return "white"

        cr_c = rcolor(v.comm_rewards)
        os_c = rcolor(v.outstanding)
        
        rew_info = ""
        if cr_c == "bright_yellow" or os_c == "bright_yellow":
            rew_info = f"\n\n [bright_green]Rewards available![/]\n Run: {self._cfg.binary} tx distribution withdraw-rewards ..."

        return (
            f"[bold]MY VALIDATOR STATUS[/]\n"
            f" Moniker: [bold]{v.moniker or d.moniker or '—'}[/]{jail}\n"
            f" Status: [{sc}]{v.status}[/]\n"
            f" Power: {v.voting_power}\n"
            f" Commission: {v.commission}\n"
            f" Commission Rewards: [{cr_c}]{v.comm_rewards} {self._cfg.denom}[/]\n"
            f" Outstanding Rewards: [{os_c}]{v.outstanding} {self._cfg.denom}[/]"
            f"{rew_info}"
        )


# ── Per-chain dashboard ───────────────────────────────────────────────────────

class ChainDashboard(Container):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg      = cfg
        self._ready    = False
        self._val_page = 0
        self._vals: list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="main-layout"):
            with Horizontal(classes="row"):
                yield NodePanel(self._cfg, classes="panel")
                yield ChainPanel(self._cfg, classes="panel")
            with Horizontal(classes="row"):
                yield NetworkPanel(self._cfg, classes="panel")
                yield MyValPanel(self._cfg, classes="panel")
            
            with Vertical(classes="panel-table"):
                yield Static(f"[bold]NETWORK VALIDATORS[/] — loading…", id="val-hdr")
                yield DataTable(id="val-tbl", show_cursor=True)
            
            with Vertical(classes="panel-log"):
                yield Static(f"[bold]📜 LOGS[/]", id="log-hdr")
                yield RichLog(id="log-area", highlight=True,
                              markup=True, max_lines=500, auto_scroll=True)

    def on_mount(self):
        tbl = self.query_one("#val-tbl", DataTable)
        tbl.add_columns(
            "NODE NAME", "STATUS",
            f"STAKE ({self._cfg.denom})", "COMMISSION%",
            "COMM REWARDS", "OUTSTANDING"
        )
        self._ready = True

    def push_data(self, d: NodeStatus):
        if not self._ready:
            return
        try:
            self.query_one(NodePanel).update_data(d)
            self.query_one(ChainPanel).update_data(d)
            self.query_one(NetworkPanel).update_data(d)
            self.query_one(MyValPanel).update_data(d)
        except Exception:
            return

        if d.validators:
            self._vals = d.validators
            self._render_val_table()

        # Live logs — append new lines
        try:
            log = self.query_one("#log-area", RichLog)
            for line in d.log_lines[-10:]:
                if line.strip():
                    line = escape(line)
                    if " INF " in line:
                        line = line.replace(" INF ", " [bright_blue]INF[/] ", 1)
                    elif " ERR " in line or " ERRO" in line:
                        line = line.replace(" ERR", " [bright_red]ERR[/]", 1)
                    elif " WRN " in line or " WARN" in line:
                        line = line.replace(" WRN", " [yellow]WRN[/]", 1)
                    log.write(line)
        except Exception:
            pass

    def _render_val_table(self):
        try:
            tbl = self.query_one("#val-tbl", DataTable)
            hdr = self.query_one("#val-hdr", Static)
        except Exception:
            return

        tbl.clear()
        total = len(self._vals)
        per_page = 15
        pages = max(1, (total + per_page - 1) // per_page)
        page  = self._vals[self._val_page * per_page: (self._val_page + 1) * per_page]

        hdr.update(
            f"[bold]NETWORK VALIDATORS[/] (PAGE {self._val_page + 1}/{pages})   "
            f"[dim]← / → : change page | Total: {total} validators[/]"
        )
        for v in page:
            s  = _sc(v["status"])
            cr = v.get("comm_rewards", "—")
            os_ = v.get("outstanding", "—")
            cr_str  = f"[bright_yellow]{cr}[/]"  if cr  not in ("—", "0", "") else "—"
            os_str  = f"[bright_yellow]{os_}[/]" if os_ not in ("—", "0", "") else "—"
            
            # Highlight our validator
            name_str = v["moniker"]
            try:
                my_moniker = self.query_one(MyValPanel)._d.validator.moniker
                if my_moniker and my_moniker == v["moniker"]:
                    name_str = f"[bold bright_cyan]v {name_str} [My Validator][/]"
            except Exception:
                pass
                
            tbl.add_row(
                name_str,
                f"[{s}]{v['status']}[/]",
                v["tokens"],
                v["commission"],
                cr_str,
                os_str,
            )

    def next_page(self):
        per_page = 15
        if (self._val_page + 1) * per_page < len(self._vals):
            self._val_page += 1
            self._render_val_table()

    def prev_page(self):
        if self._val_page > 0:
            self._val_page -= 1
            self._render_val_table()


# ── Main App ──────────────────────────────────────────────────────────────────

class CosmosMonitor(App):
    CSS = """
    Screen { background: #0d1117; }
    
    .mini-logo {
        text-align: center;
        width: 100%;
        margin: 1 0;
    }
    
    TabbedContent { height: 1fr; }

    #main-layout {
        height: 100%;
        layout: vertical;
        padding: 0 1;
    }

    .row {
        height: auto;
        min-height: 9;
        margin-bottom: 1;
    }

    .panel {
        width: 1fr;
        height: 100%;
        border: solid #4d5562;
        padding: 1 2;
        margin-right: 1;
    }
    
    .panel-table {
        height: 19;
        border: solid #4d5562;
        padding: 0 2;
        margin-bottom: 1;
        margin-right: 1;
    }
    
    .panel-log {
        height: 1fr;
        border: solid #4d5562;
        padding: 0 2;
        margin-right: 1;
    }

    #val-hdr { margin-top: 1; margin-bottom: 1; text-align: center; }
    #val-tbl {
        height: 1fr;
        background: transparent;
    }

    #log-hdr  { margin-top: 1; margin-bottom: 1; text-align: left; }
    #log-area {
        height: 1fr;
        background: transparent;
    }

    DataTable                      { background: transparent; }
    DataTable > .datatable--header { background: #161b22; color: #8b949e; }
    DataTable > .datatable--cursor { background: #1f2937; }
    DataTable > .datatable--row    { height: 1; }
    """

    BINDINGS = [
        Binding("q",      "quit",       "Quit"),
        Binding("ctrl+c", "quit",       "Quit"),
        Binding("right",  "next_page",  "Next Page"),
        Binding("left",   "prev_page",  "Prev Page"),
        Binding("r",      "do_refresh", "Refresh"),
        Binding("h",      "show_help",  "Help"),
    ]

    def __init__(self, chains: list[ChainConfig],
                 refresh_interval: int = 5, **kw):
        super().__init__(**kw)
        self._chains   = chains
        self._interval = refresh_interval

    def compose(self) -> ComposeResult:
        yield Static("[bold bright_cyan]OSHVANK VALIDATOR DASHBOARD v0.2.26[/]", classes="mini-logo")
        with TabbedContent():
            for cfg in self._chains:
                with TabPane(cfg.name, id=f"tab-{_tab_id(cfg)}"):
                    yield ChainDashboard(cfg, id=f"dash-{_tab_id(cfg)}")
        yield Footer()

    def on_mount(self):
        self.title     = "cosmos-monitor"
        self.set_timer(0.8, self._kick_all)
        self.set_interval(self._interval, self._kick_all)

    def _kick_all(self):
        for cfg in self._chains:
            self._spawn_fetch(cfg)

    def _spawn_fetch(self, cfg: ChainConfig):
        async def _worker():
            loop = asyncio.get_event_loop()
            ns   = await loop.run_in_executor(None, fetch_node_status, cfg)
            did  = f"dash-{_tab_id(cfg)}"
            try:
                dash = self.query_one(f"#{did}", ChainDashboard)
                dash.push_data(ns)
            except Exception:
                pass
        asyncio.create_task(_worker())

    def _active_dash(self) -> ChainDashboard | None:
        try:
            active = self.query_one(TabbedContent).active
            for cfg in self._chains:
                if active == f"tab-{_tab_id(cfg)}":
                    return self.query_one(f"#dash-{_tab_id(cfg)}", ChainDashboard)
        except Exception:
            pass
        return None

    def action_next_page(self):
        d = self._active_dash()
        if d: d.next_page()

    def action_prev_page(self):
        d = self._active_dash()
        if d: d.prev_page()

    def action_do_refresh(self):
        self._kick_all()

    def action_show_help(self):
        self.notify(
            "q=quit  ←/→=validator pages  r=refresh  Tab=switch chain",
            title="Keyboard shortcuts",
        )
