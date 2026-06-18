"""cosmos-monitor — Textual TUI dashboard (textual 8.x compatible)."""

import asyncio
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import (
    Footer, Header, Static, TabbedContent, TabPane,
    DataTable, RichLog,
)

from .chain import ChainConfig
from .fetcher import NodeStatus, fetch_node_status

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.ansi")


def _load_logo() -> str:
    try:
        return Path(LOGO_PATH).resolve().read_text(encoding="utf-8")
    except Exception:
        return ""


def _fmt_uptime(sec: int) -> str:
    if sec < 60:    return f"{sec}s"
    if sec < 3600:  return f"{sec//60}m"
    if sec < 86400: return f"{sec//3600}h {(sec % 3600)//60}m"
    return f"{sec//86400}d {(sec % 86400)//3600}h"


def _bar(pct: float, w: int = 20) -> str:
    n = int(w * min(pct, 100) / 100)
    return "█" * n + "░" * (w - n)


def _sc(status: str) -> str:
    return {"BONDED": "bright_green", "UNBONDING": "yellow",
            "UNBONDED": "red"}.get(status, "dim")


def _tab_id(cfg: ChainConfig) -> str:
    return cfg.chain_id.replace("_", "-").replace(".", "-")


# ── Logo (compact) ────────────────────────────────────────────────────────────

class LogoPanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg  = cfg
        self._logo = _load_logo()

    def render(self):
        from rich.text import Text
        from rich.align import Align
        from rich.console import Group
        c = self._cfg.color
        if self._logo:
            # Scale down: keep ANSI but let the fixed 24-char width constrain it
            logo = Align.center(Text.from_ansi(self._logo))
        else:
            logo = Align.center(Text("[ OSHVANK ]", style="bold white"))
        return Group(
            logo,
            Align.center(Text("─" * 18, style="dim")),
            Align.center(Text("OSHVANK",            style="bold white")),
            Align.center(Text("Validator Dashboard", style=c)),
            Align.center(Text(self._cfg.name,        style=f"bold {c}")),
            Align.center(Text(self._cfg.chain_id,    style="dim")),
        )


# ── Node + Chain status ───────────────────────────────────────────────────────

class StatusPanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg = cfg
        self._d   = NodeStatus()

    def update_data(self, d: NodeStatus):
        self._d = d
        self.refresh()

    def render(self):
        d, c = self._d, self._cfg.color
        ok = "[bright_green]✓[/]"
        no = "[red]✗[/]"
        warn = "[yellow]⚠[/]"

        proc = f"{ok} Running  [dim]pid {d.pid}[/]" if d.running else f"{no} [red]Not running[/]"
        rpc  = f"{ok} [dim]:{self._cfg.ports.rpc}[/]" if d.running else f"{no} [red]:{self._cfg.ports.rpc} down[/]"
        mc   = "yellow" if d.mem_pct  > 70 else "bright_green"
        dc   = "yellow" if d.disk_pct > 80 else "white"
        sc   = "bright_green" if not d.syncing else "yellow"
        sbar = f"[{sc}]{_bar(d.sync_pct, 22)}[/] [{sc}]{d.sync_pct:.1f}%[/]"
        sync = "[bright_green]✓ In Sync[/]" if not d.syncing else f"[yellow]⟳ Syncing[/]"
        p    = self._cfg.ports

        return (
            f"[bold {c}]◈ NODE[/]\n"
            f" [dim]Process[/] {proc}\n"
            f" [dim]RPC    [/] {rpc}\n"
            f" [dim]Uptime [/] {_fmt_uptime(d.uptime_sec)}\n"
            f" [dim]Memory [/] [{mc}]{d.mem_pct:.1f}%[/]\n"
            f" [dim]Disk   [/] [{dc}]{d.disk_pct:.1f}%[/]\n"
            f" [dim]Version[/] [{c}]{d.version or '—'}[/]\n"
            f"\n[bold {c}]⛓ CHAIN[/]\n"
            f" [dim]Status [/] {sync}\n"
            f" {sbar}\n"
            f" [dim]Height [/] [{c}]{d.latest_block:,}[/]\n"
            f" [dim]Peers  [/] [bright_green]{d.peers}[/] connected\n"
            f" [dim]Latency[/] {d.latency_ms}ms\n"
            f"\n[bold {c}]⚙ PORTS[/]\n"
            f" [dim]RPC[/]  :{p.rpc}  [dim]P2P[/] :{p.p2p}\n"
            f" [dim]gRPC[/] :{p.grpc}  [dim]REST[/] :{p.rest}"
        )


# ── Network + My Validator ────────────────────────────────────────────────────

class NetworkPanel(Static):
    def __init__(self, cfg: ChainConfig, **kw):
        super().__init__(**kw)
        self._cfg = cfg
        self._d   = NodeStatus()

    def update_data(self, d: NodeStatus):
        self._d = d
        self.refresh()

    def render(self):
        d, c = self._d, self._cfg.color
        v    = d.validator
        nid  = (d.node_id[:20] + "…") if len(d.node_id) > 20 else (d.node_id or "—")
        sc   = _sc(v.status)
        jail = "  [bold red]JAILED[/]" if v.jailed else ""

        # Rewards color: highlight if > 0
        def rcolor(val: str) -> str:
            try:
                return "bright_yellow" if float(val.replace(",","")) > 0 else "white"
            except Exception:
                return "white"

        cr_c = rcolor(v.comm_rewards)
        os_c = rcolor(v.outstanding)

        return (
            f"[bold {c}]🌐 NETWORK[/]\n"
            f" [dim]Node ID [/] [{c}]{nid}[/]\n"
            f" [dim]Moniker [/] [{c}]{d.moniker or self._cfg.moniker or '—'}[/]\n"
            f" [dim]Chain   [/] {d.chain_id or self._cfg.chain_id}\n"
            f" [dim]Network [/] {d.network or '—'}\n"
            f" [dim]Latency [/] {d.latency_ms}ms\n"
            f"\n[bold {c}]🏛 MY VALIDATOR[/]\n"
            f" [dim]Name    [/] [bold {c}]{v.moniker or d.moniker or '—'}[/]{jail}\n"
            f" [dim]Status  [/] [{sc}]{v.status}[/]\n"
            f" [dim]Power   [/] {v.voting_power}\n"
            f" [dim]Comm.   [/] {v.commission}\n"
            f" [dim]Rewards [/] [{cr_c}]{v.comm_rewards} {self._cfg.denom}[/]\n"
            f" [dim]Outstand[/] [{os_c}]{v.outstanding} {self._cfg.denom}[/]"
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
        c = self._cfg.color
        with Horizontal(id="top-row"):
            # Left column: compact logo
            yield LogoPanel(self._cfg, id="logo-panel")
            # Middle column: node + chain status
            yield StatusPanel(self._cfg, id="status-panel")
            # Right column: network + my validator
            yield NetworkPanel(self._cfg, id="net-panel")
        # Validators table
        yield Static(f"[bold {c}]📋 VALIDATORS — loading…[/]", id="val-hdr")
        yield DataTable(id="val-tbl", show_cursor=True)
        # Logs
        yield Static(f"[bold {c}]📜 LIVE LOGS[/]", id="log-hdr")
        yield RichLog(id="log-area", highlight=True,
                      markup=True, max_lines=500, auto_scroll=True)

    def on_mount(self):
        tbl = self.query_one("#val-tbl", DataTable)
        tbl.add_columns(
            "NAME", "STATUS",
            f"STAKE ({self._cfg.denom})", "COMM%",
            "COMM REWARDS", "OUTSTANDING",
        )
        self._ready = True

    def push_data(self, d: NodeStatus):
        if not self._ready:
            return
        try:
            self.query_one("#status-panel", StatusPanel).update_data(d)
            self.query_one("#net-panel",    NetworkPanel).update_data(d)
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
                    # Colorize log levels
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
        pages = max(1, (total + 7) // 8)
        page  = self._vals[self._val_page * 8: (self._val_page + 1) * 8]
        c     = self._cfg.color

        hdr.update(
            f"[bold {c}]📋 VALIDATORS  "
            f"page {self._val_page + 1}/{pages}  ({total} total)  "
            f"← / → to page[/]"
        )
        for v in page:
            s  = _sc(v["status"])
            cr = v.get("comm_rewards", "—")
            os_ = v.get("outstanding", "—")
            # Color rewards if non-zero
            cr_str  = f"[bright_yellow]{cr}[/]"  if cr  not in ("—", "0", "") else "—"
            os_str  = f"[bright_yellow]{os_}[/]" if os_ not in ("—", "0", "") else "—"
            tbl.add_row(
                v["moniker"],
                f"[{s}]{v['status']}[/]",
                v["tokens"],
                v["commission"],
                cr_str,
                os_str,
            )

    def next_page(self):
        if (self._val_page + 1) * 8 < len(self._vals):
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

    /* Top row: 3 columns */
    #top-row {
        height: auto;
        width: 1fr;
    }
    #logo-panel {
        width: 26;
        min-width: 26;
        max-width: 26;
        border: solid #2a2a3a;
        padding: 0 1;
        height: auto;
    }
    #status-panel {
        width: 1fr;
        border: solid #1e3a2a;
        padding: 0 1;
        height: auto;
    }
    #net-panel {
        width: 1fr;
        border: solid #1e2a3a;
        padding: 0 1;
        height: auto;
    }

    /* Validators */
    #val-hdr { padding: 0 1; margin-top: 1; }
    #val-tbl {
        height: 12;
        margin: 0 0;
        border: solid #21262d;
    }

    /* Logs */
    #log-hdr  { padding: 0 1; margin-top: 1; }
    #log-area {
        height: 10;
        margin: 0 0;
        border: solid #21262d;
        background: #060809;
    }

    DataTable                      { background: #0d1117; }
    DataTable > .datatable--header { background: #161b22; color: #8b949e; }
    DataTable > .datatable--cursor { background: #1f2937; }
    DataTable > .datatable--row    { height: 1; }
    """

    BINDINGS = [
        Binding("q",      "quit",       "Quit"),
        Binding("ctrl+c", "quit",       "Quit"),
        Binding("right",  "next_page",  "→ validators"),
        Binding("left",   "prev_page",  "← validators"),
        Binding("r",      "do_refresh", "Refresh"),
        Binding("h",      "show_help",  "Help"),
    ]

    def __init__(self, chains: list[ChainConfig],
                 refresh_interval: int = 5, **kw):
        super().__init__(**kw)
        self._chains   = chains
        self._interval = refresh_interval

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            for cfg in self._chains:
                with TabPane(cfg.name, id=f"tab-{_tab_id(cfg)}"):
                    yield ChainDashboard(cfg, id=f"dash-{_tab_id(cfg)}")
        yield Footer()

    def on_mount(self):
        self.title     = "cosmos-monitor"
        self.sub_title = "Oshvank Validator Dashboard"
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
