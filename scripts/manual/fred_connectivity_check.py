"""Read-only sanity check that macro_data.providers.fred.FredMacroProvider
works against the real FRED (Federal Reserve Economic Data) API. Fetches a
handful of recent observations for one series and prints them. Never
places an order and has no side effect beyond the one HTTP GET -- this is
the FRED equivalent of scripts/manual/mt5_connectivity_check.py.

Get a free API key (instant, no approval wait):
    https://fred.stlouisfed.org/docs/api/api_key.html

Setup:
    pip install -e .
    $env:FRED_API_KEY = "<your key>"     # PowerShell
    export FRED_API_KEY="<your key>"     # bash

Optional overrides:
    $env:FRED_SERIES_ID = "T10Y2Y"   # default: 10Y-2Y Treasury yield
                                      # spread, a real, well-known series --
                                      # any valid FRED series ID works
    $env:FRED_LIMIT = "10"           # how many recent observations to fetch

Run (from the repository root):
    python scripts/manual/fred_connectivity_check.py
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main() -> None:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("Missing required environment variable: FRED_API_KEY", file=sys.stderr)
        print(
            "Get a free key: https://fred.stlouisfed.org/docs/api/api_key.html",
            file=sys.stderr,
        )
        sys.exit(1)

    series_id = os.environ.get("FRED_SERIES_ID", "T10Y2Y")
    limit = int(os.environ.get("FRED_LIMIT", "10"))

    from macro_data.providers.fred import FredMacroProvider

    provider = FredMacroProvider(api_key)
    print(f"Fetching {limit} recent observations for FRED series '{series_id}'...")
    try:
        observations = await provider.fetch_series(series_id, limit=limit)
    except Exception as exc:  # noqa: BLE001 - report any failure, this is a diagnostic script
        print(f"FAILED to fetch '{series_id}': {exc}", file=sys.stderr)
        sys.exit(1)

    if not observations:
        print("No observations returned -- check the series ID.")
        return

    print(f"Fetched {len(observations)} observations:")
    for observation in observations:
        value_text = (
            f"{observation.value:.4f}" if observation.value is not None else "(no data)"
        )
        print(f"  {observation.observed_on.isoformat()}: {value_text}")


if __name__ == "__main__":
    asyncio.run(main())
