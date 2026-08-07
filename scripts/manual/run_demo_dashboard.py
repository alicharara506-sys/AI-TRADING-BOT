"""One-command local preview: seeds demo.db with synthetic data (if it
doesn't already exist) and launches the Streamlit dashboard against it, so
you can just run this and open the localhost URL it prints -- no MT5
terminal, broker account, or credentials of any kind required.

See scripts/manual/seed_demo_data.py's docstring for exactly what "demo"
means here: synthetic bars, but real signals from the real
SignalFusionStrategy. The dashboard itself shows a persistent warning
banner (--demo) so nothing on the page can be mistaken for real data.

Setup:
    pip install -e ".[dashboard]"

Run (from the repository root):
    python scripts/manual/run_demo_dashboard.py

Then open the "Local URL" Streamlit prints (typically
http://localhost:8501) in your browser. Stop with Ctrl+C.

Optional:
    python scripts/manual/run_demo_dashboard.py --reset   # regenerate demo.db
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# python puts this script's own directory (scripts/manual/) at sys.path[0],
# so seed_demo_data (a plain sibling module, not part of the installed
# package) is importable bare -- no package-relative import needed.
from seed_demo_data import DEMO_DB_PATH, DEMO_SYMBOL_NAME, DEMO_TIMEFRAME, seed


def main() -> None:
    reset = "--reset" in sys.argv
    db_file = Path(DEMO_DB_PATH)

    if reset or not db_file.exists():
        print(f"Seeding {DEMO_DB_PATH} with synthetic demo data...")
        signal_count = seed(db_path=DEMO_DB_PATH)
        print(f"Recorded {signal_count} real signal(s) from synthetic bars.\n")
    else:
        print(f"{DEMO_DB_PATH} already exists -- reusing it (pass --reset to regenerate).\n")

    app_path = Path(__file__).parent / "dashboard" / "app.py"
    print("Launching the Streamlit dashboard -- open the Local URL below in your browser.")
    print("Press Ctrl+C to stop.\n")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--",
            "--db-path",
            DEMO_DB_PATH,
            "--symbol",
            DEMO_SYMBOL_NAME,
            "--timeframe",
            DEMO_TIMEFRAME.value,
            "--demo",
        ],
        check=False,
    )


if __name__ == "__main__":
    main()
