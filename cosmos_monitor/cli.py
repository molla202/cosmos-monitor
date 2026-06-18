#!/usr/bin/env python3
"""cosmos-monitor CLI entry point."""

import argparse
import sys

from .chain import detect_chains
from . import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="cosmos-monitor",
        description="Multi-chain Cosmos validator TUI dashboard by Oshvank",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--home", "-H",
        action="append",
        metavar="DIR",
        help="Chain home directory (e.g. ~/.pchain). Can be specified multiple times.",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"cosmos-monitor {__version__}",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all auto-detected chains and exit",
    )
    parser.add_argument(
        "--refresh", "-r",
        type=int,
        default=5,
        metavar="SEC",
        help="Refresh interval in seconds (default: 5)",
    )

    args = parser.parse_args()

    # Detect chains
    chains = detect_chains(extra_homes=args.home or [])

    if not chains:
        print("No Cosmos chains detected.")
        print()
        print("cosmos-monitor scans every ~/.xxx directory automatically.")
        print("Make sure your node home contains config/config.toml")
        print()
        print("Or specify manually:")
        print("  cosmos-monitor --home ~/.mychain")
        sys.exit(1)

    if args.list:
        print(f"cosmos-monitor {__version__} — detected {len(chains)} chain(s):\n")
        for c in chains:
            status = "✓" if _is_running(c.binary) else "○"
            print(f"  {status} {c.name:<22} chain_id={c.chain_id}")
            print(f"      home   : {c.home_dir}")
            print(f"      binary : {c.binary}")
            print(f"      ports  : RPC={c.ports.rpc}  P2P={c.ports.p2p}  gRPC={c.ports.grpc}  REST={c.ports.rest}")
            if c.moniker:
                print(f"      moniker: {c.moniker}")
            print()
        print("  ✓ = process running   ○ = process not detected")
        sys.exit(0)

    # Launch TUI
    from .dashboard import CosmosMonitor
    app = CosmosMonitor(chains=chains, refresh_interval=args.refresh)
    app.run()


def _is_running(binary: str) -> bool:
    """Quick check if binary process is running."""
    try:
        import subprocess
        r = subprocess.run(["pgrep", "-f", binary], capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


if __name__ == "__main__":
    main()
