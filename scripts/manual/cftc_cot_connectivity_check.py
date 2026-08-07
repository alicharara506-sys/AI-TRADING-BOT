"""Read-only sanity check that cot_data.providers.cftc.CftcCotProvider
works against the real CFTC (Commodity Futures Trading Commission) public
Socrata API. Fetches a handful of recent Commitments of Traders (COT)
observations for one contract market and prints them. Never places an
order and has no side effect beyond the one HTTP GET -- this is the CFTC
equivalent of scripts/manual/fred_connectivity_check.py.

No API key or registration required -- the CFTC's public reporting API is
open to anyone with an internet connection.

Setup:
    pip install -e .

Optional overrides:
    $env:COT_CONTRACT_MARKET_CODE = "099741"   # PowerShell -- default:
                                                # EURO FX (Chicago
                                                # Mercantile Exchange), a
                                                # real, well-known code --
                                                # any valid CFTC contract
                                                # market code works
    export COT_CONTRACT_MARKET_CODE="099741"   # bash
    $env:COT_LIMIT = "5"           # how many recent weekly reports to fetch
    $env:COT_APP_TOKEN = "..."     # optional Socrata app token (raises the
                                    # anonymous rate limit; not required)

Run (from the repository root):
    python scripts/manual/cftc_cot_connectivity_check.py
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main() -> None:
    contract_market_code = os.environ.get("COT_CONTRACT_MARKET_CODE", "099741")
    limit = int(os.environ.get("COT_LIMIT", "5"))
    app_token = os.environ.get("COT_APP_TOKEN")

    from cot_data.providers.cftc import CftcCotProvider

    provider = CftcCotProvider(app_token=app_token)
    print(
        f"Fetching {limit} recent Commitments of Traders reports for "
        f"contract market code '{contract_market_code}'..."
    )
    try:
        observations = await provider.fetch_observations(contract_market_code, limit=limit)
    except Exception as exc:  # noqa: BLE001 - report any failure, this is a diagnostic script
        print(f"FAILED to fetch '{contract_market_code}': {exc}", file=sys.stderr)
        sys.exit(1)

    if not observations:
        print("No observations returned -- check the contract market code.")
        return

    print(f"Fetched {len(observations)} observations:")
    for observation in observations:
        print(
            f"  {observation.report_date.isoformat()} "
            f"{observation.market_and_exchange_name}: "
            f"noncomm long={observation.noncommercial_long} "
            f"short={observation.noncommercial_short}, "
            f"comm long={observation.commercial_long} "
            f"short={observation.commercial_short}, "
            f"open interest={observation.open_interest}"
        )


if __name__ == "__main__":
    asyncio.run(main())
