"""Read-only connectivity check against a REAL MetaTrader 5 terminal.

This must run on the same Windows machine as your MT5 terminal -- the
`MetaTrader5` pip package talks to the terminal over local IPC and cannot
reach it from a remote machine or a non-Windows OS. It cannot be run from
this repository's cloud/CI environment.

What this proves: that MT5Connector (connectors/mt5/connector.py), tested
throughout this project only against a fake MT5Api, also works against the
real package and a real terminal. It has never been exercised against the
real package before -- if something in the mirrored MT5Api Protocol
(connectors/mt5/api.py) doesn't match the installed MetaTrader5 version,
this is where that would first surface. Report back whatever error you see
so it can be fixed at the root cause.

Safety: this script only reads data (connect, account state, symbol info,
open positions). It never calls submit_order, modify_position, or
close_position. Nothing here can place, modify, or close a trade.

Setup (PowerShell, run once per session):
    py -m venv .venv
    .venv\\Scripts\\Activate.ps1
    pip install -e .
    pip install MetaTrader5

    $env:MT5_LOGIN = "900784"
    $env:MT5_PASSWORD = "<your demo account password>"
    $env:MT5_SERVER = "SupremeFX-Server"

Optional: if your broker suffixes its symbol names (e.g. Market Watch shows
"EURUSD.gc" rather than plain "EURUSD"), set the suffix separately -- symbol
names are matched case-sensitively against the broker's own list, and this
platform always uppercases the base name, so a lowercase suffix typed into
MT5_CHECK_SYMBOL directly would silently fail to match:
    $env:MT5_CHECK_SYMBOL = "EURUSD"
    $env:MT5_SYMBOL_SUFFIX = ".gc"

Run (from the repository root, with the venv active):
    python scripts\\manual\\mt5_connectivity_check.py

Do not hardcode the password above or commit it -- .gitignore already
excludes .env files for exactly this reason (see
docs/security/phase-14-review.md). Set the environment variables in your
shell each session, or via a local .env file loaded by your shell profile.
"""

from __future__ import annotations

import asyncio
import os
import sys


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


async def main() -> None:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError:
        print(
            "The real MetaTrader5 package isn't installed. Run:\n"
            "    pip install MetaTrader5\n"
            "(Windows only -- this package cannot install on Linux/macOS.)",
            file=sys.stderr,
        )
        sys.exit(1)

    from connectors.mt5.connector import MT5Connector
    from connectors.mt_common.symbols import SymbolMapper
    from core.event_bus.bus import EventBus
    from core.interfaces.types import Symbol

    login = int(_require_env("MT5_LOGIN"))
    password = _require_env("MT5_PASSWORD")
    server = _require_env("MT5_SERVER")
    symbol_name = os.environ.get("MT5_CHECK_SYMBOL", "EURUSD")
    symbol_suffix = os.environ.get("MT5_SYMBOL_SUFFIX", "")

    event_bus = EventBus()
    connector = MT5Connector(
        mt5,
        event_bus,
        login=login,
        password=password,
        server=server,
        symbol_mapper=SymbolMapper(suffix=symbol_suffix),
    )

    print(f"Connecting to server='{server}' login={login} ...")
    try:
        await connector.connect()
    except ConnectionError as exc:
        print(f"FAILED to connect: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Connected: {connector.is_connected()}")

    try:
        account = await connector.get_account_state()
        print(
            f"Account: balance={account.balance} {account.currency}, "
            f"equity={account.equity}, free_margin={account.free_margin}"
        )

        symbol = Symbol(name=symbol_name)
        try:
            info = await connector.get_symbol_info(symbol)
            print(
                f"Symbol {symbol_name}: digits={info.digits}, point={info.point}, "
                f"min_volume={info.min_volume}, max_volume={info.max_volume}, "
                f"account_mode={info.account_mode.value}"
            )
        except LookupError as exc:
            print(f"Symbol lookup failed for '{symbol_name}': {exc}")

        positions = await connector.get_open_positions()
        print(f"Open positions: {len(positions)}")
        for position in positions:
            print(
                f"  {position.symbol.canonical} {position.side.value} "
                f"{position.volume} @ {position.open_price}"
            )

        print("\nConnectivity check passed -- no orders were placed.")
    finally:
        await connector.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
