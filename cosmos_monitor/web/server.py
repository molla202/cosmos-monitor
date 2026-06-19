"""
cosmos-monitor web dashboard — FastAPI backend.

Re-uses chain.py (detection) and fetcher.py (RPC/REST polling) as-is —
no duplicated logic between the TUI and the web dashboard.

Run with:
    cosmos-monitor --web
or directly:
    python -m cosmos_monitor.web.server
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..chain import ChainConfig, detect_chains
from ..config import add_custom_chain, add_hidden_chain
from ..fetcher import NodeStatus, fetch_node_status

log = logging.getLogger("cosmos_monitor.web")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _poll_task
    await _refresh_chains(broadcast=False)
    _poll_task = asyncio.create_task(_poll_loop())
    yield
    if _poll_task:
        _poll_task.cancel()


app = FastAPI(title="cosmos-monitor", lifespan=_lifespan)

# ── Shared state (single process, single asyncio loop) ────────────────────────
_refresh_interval: int = 5
_extra_homes: List[str] = []
_chains_cache: List[ChainConfig] = []
_clients: List[WebSocket] = []
_poll_task: Optional[asyncio.Task] = None


def _cfg_to_dict(cfg: ChainConfig) -> dict:
    return {
        "chain_id": cfg.chain_id,
        "name": cfg.name,
        "denom": cfg.denom,
        "binary": cfg.binary,
        "color": cfg.color,
        "home_dir": cfg.home_dir,
        "moniker": cfg.moniker,
        "ports": {
            "rpc": cfg.ports.rpc,
            "p2p": cfg.ports.p2p,
            "grpc": cfg.ports.grpc,
            "rest": cfg.ports.rest,
        },
    }


def _status_to_dict(s: NodeStatus) -> dict:
    return asdict(s)


async def _broadcast(payload: dict) -> None:
    if not _clients:
        return
    msg = json.dumps(payload)
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in _clients:
            _clients.remove(d)


async def _refresh_chains(broadcast: bool = True) -> None:
    global _chains_cache
    loop = asyncio.get_event_loop()
    _chains_cache = await loop.run_in_executor(
        None, lambda: detect_chains(extra_homes=_extra_homes)
    )
    if broadcast:
        await _broadcast(
            {"type": "chains", "data": [_cfg_to_dict(c) for c in _chains_cache]}
        )


async def _poll_loop() -> None:
    """Mirrors dashboard.py's _kick_all(): fetch every chain on a timer."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            for cfg in list(_chains_cache):
                status = await loop.run_in_executor(None, fetch_node_status, cfg)
                await _broadcast(
                    {
                        "type": "status",
                        "chain_id": cfg.chain_id,
                        "data": _status_to_dict(status),
                    }
                )
        except Exception:
            log.exception("poll loop error")
        await asyncio.sleep(_refresh_interval)


# ── REST API ────────────────────────────────────────────────────────────────

@app.get("/api/chains")
async def api_chains():
    return [_cfg_to_dict(c) for c in _chains_cache]


@app.get("/api/status/{chain_id}")
async def api_status(chain_id: str):
    loop = asyncio.get_event_loop()
    for cfg in _chains_cache:
        if cfg.chain_id == chain_id:
            status = await loop.run_in_executor(None, fetch_node_status, cfg)
            return _status_to_dict(status)
    return {"error": "chain not found"}


class AddNodeRequest(BaseModel):
    home_dir: str


class HideNodeRequest(BaseModel):
    target: str  # chain_id or home_dir


@app.post("/api/nodes/add")
async def api_add_node(req: AddNodeRequest):
    add_custom_chain(req.home_dir.strip())
    await _refresh_chains()
    return {"ok": True, "chains": [_cfg_to_dict(c) for c in _chains_cache]}


@app.post("/api/nodes/hide")
async def api_hide_node(req: HideNodeRequest):
    add_hidden_chain(req.target.strip())
    await _refresh_chains()
    return {"ok": True, "chains": [_cfg_to_dict(c) for c in _chains_cache]}


@app.post("/api/refresh")
async def api_refresh():
    await _refresh_chains()
    return {"ok": True}


# ── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    try:
        await ws.send_text(
            json.dumps(
                {
                    "type": "chains",
                    "data": [_cfg_to_dict(c) for c in _chains_cache],
                    "refresh_interval": _refresh_interval,
                }
            )
        )
        # Push an immediate status snapshot so the browser doesn't wait
        # for the next poll tick.
        loop = asyncio.get_event_loop()
        for cfg in list(_chains_cache):
            status = await loop.run_in_executor(None, fetch_node_status, cfg)
            await ws.send_text(
                json.dumps(
                    {
                        "type": "status",
                        "chain_id": cfg.chain_id,
                        "data": _status_to_dict(status),
                    }
                )
            )
        while True:
            # We don't expect client -> server messages other than pings,
            # but reading keeps the connection alive and lets us detect
            # disconnects promptly.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("websocket error")
    finally:
        if ws in _clients:
            _clients.remove(ws)



# Static files (the dashboard itself) — mounted last so /api/* and /ws above
# always take precedence over the catch-all "/" mount.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def run(
    host: str = "0.0.0.0",
    port: int = 8000,
    refresh_interval: int = 5,
    extra_homes: Optional[List[str]] = None,
) -> None:
    """Entry point used by `cosmos-monitor --web`."""
    global _refresh_interval, _extra_homes
    _refresh_interval = max(1, refresh_interval)
    _extra_homes = extra_homes or []

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
