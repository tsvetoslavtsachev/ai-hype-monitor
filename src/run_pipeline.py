"""
run_pipeline.py — AI Hype Monitor · Главен Pipeline
====================================================
Оркестрира всички модули в правилния ред.

Режими:
  --daily     : само цени + hype_index (за дневния cron)
  --quarterly : цени + SEC filings + NLP + hype_index (за тримесечния cron)
  --full      : всичко (за ръчно стартиране)
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fetch_prices
import calc_hype_index


def log(msg: str):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_daily(price_archive_root=None):
    """Дневен pipeline: цени → hype_index."""
    log("=== DAILY PIPELINE START ===")

    log("Step 1/2: Fetch Prices")
    try:
        fetch_prices.run(price_archive_root=price_archive_root, log=log)
    except Exception as e:
        log(f"ERROR in fetch_prices: {e}")
        traceback.print_exc()
        sys.exit(1)

    log("Step 2/2: Calculate Hype Index")
    try:
        calc_hype_index.run(skip_valuation_pe=False, log=log)
    except Exception as e:
        log(f"ERROR in calc_hype_index: {e}")
        traceback.print_exc()
        sys.exit(1)

    log("=== DAILY PIPELINE COMPLETE ===")


def run_quarterly():
    """Тримесечен pipeline: SEC filings → NLP → hype_index."""
    import fetch_sec_edgar
    import analyze_rhetoric

    log("=== QUARTERLY PIPELINE START ===")

    log("Step 1/4: Fetch Prices (refresh)")
    try:
        fetch_prices.run(log=log)
    except Exception as e:
        log(f"ERROR in fetch_prices: {e}")
        traceback.print_exc()

    log("Step 2/4: Fetch SEC EDGAR Filings")
    try:
        fetch_sec_edgar.run(fetch_text=True, log=log)
    except Exception as e:
        log(f"ERROR in fetch_sec_edgar: {e}")
        traceback.print_exc()

    log("Step 3/4: Analyze Rhetoric (NLP)")
    try:
        analyze_rhetoric.run(log=log)
    except Exception as e:
        log(f"ERROR in analyze_rhetoric: {e}")
        traceback.print_exc()

    log("Step 4/4: Calculate Hype Index")
    try:
        calc_hype_index.run(log=log)
    except Exception as e:
        log(f"ERROR in calc_hype_index: {e}")
        traceback.print_exc()
        sys.exit(1)

    log("=== QUARTERLY PIPELINE COMPLETE ===")


def main():
    parser = argparse.ArgumentParser(description="AI Hype Monitor Pipeline")
    parser.add_argument("--daily", action="store_true", help="Дневен режим (цени + индекс)")
    parser.add_argument("--quarterly", action="store_true", help="Тримесечен режим (+ SEC + NLP)")
    parser.add_argument("--full", action="store_true", help="Пълен режим")
    parser.add_argument(
        "--price-archive-root",
        type=str,
        default=None,
        help="Път до price-archive checkout (default: ../price-archive)",
    )
    args = parser.parse_args()

    price_archive_root = Path(args.price_archive_root) if args.price_archive_root else None

    if args.quarterly or args.full:
        run_quarterly()
    else:
        # Default: daily
        run_daily(price_archive_root=price_archive_root)


if __name__ == "__main__":
    main()
