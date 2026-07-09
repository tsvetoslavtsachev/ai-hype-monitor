"""
spotcheck_revenue.py — валидира F-крак revenue срещу 8-K корпуса (Фаза 1 гейт).
=============================================================================
За зададени тикери: взима ПОСЛЕДНОТО тримесечно revenue от facts store (PIT),
намира съответното earnings 8-K (raw корпус — filing веднага след period_end)
и проверява дали същата сума ($ млрд/млн) присъства в текста (толеранс 1%).
Това е независима кръстосана проверка: XBRL числата срещу думите в отчета.

Offline към facts store + raw корпус; НЕ пише нищо. Печата таблица.
"""

import glob
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts_store as fs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "app" / "data" / "corpus" / "raw"

# задължителни + още 5 (общо 10)
TICKERS = ["NVDA", "MSFT", "META", "AMD", "AMAT", "AMZN", "ORCL", "MU", "CRM", "QCOM"]

_FIG = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|B|M)\b", re.IGNORECASE)


def dollar_figures(text: str) -> list:
    """Всички $-суми (billion/million) в текста -> абсолютни USD."""
    out = []
    for num, unit in _FIG.findall(text):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        u = unit.lower()
        if u in ("billion", "b"):
            out.append(v * 1e9)
        elif u in ("million", "m"):
            out.append(v * 1e6)
    return out


def _raw_for_quarter(ticker: str, period_end: str) -> str:
    """Earnings 8-K точно след period_end (filing в (period_end, +70 дни])."""
    pe = date.fromisoformat(period_end)
    best, best_gap = None, 10**9
    for f in glob.glob(str(RAW / f"{ticker}__*.txt")):
        fd = os.path.basename(f).split("__")[2].replace(".txt", "")
        try:
            gap = (date.fromisoformat(fd) - pe).days
        except ValueError:
            continue
        if 0 <= gap <= 70 and gap < best_gap:
            best, best_gap = f, gap
    return best


def main():
    print("=== Phase 1 spot-check: facts-store revenue vs 8-K press release ===")
    print(f"{'ticker':6} {'period_end':11} {'facts_rev($B)':>13} "
          f"{'nearest_8K_fig($B)':>18} {'diff%':>7}  verdict  raw_file")
    npass = 0
    checked = 0
    for t in TICKERS:
        rec = fs.latest(t, "revenue")
        if not rec:
            print(f"{t:6} {'-':11} {'None':>13} {'-':>18} {'-':>7}  NO_FACT")
            continue
        v = rec["value"]
        pe = rec["period_end"]
        raw = _raw_for_quarter(t, pe)
        if not raw:
            print(f"{t:6} {pe:11} {v/1e9:13.3f} {'-':>18} {'-':>7}  NO_8K")
            continue
        text = open(raw, encoding="utf-8", errors="ignore").read()
        figs = dollar_figures(text)
        # най-близката $-сума до фактическото revenue
        near = min(figs, key=lambda x: abs(x - v)) if figs else None
        checked += 1
        if near is None:
            print(f"{t:6} {pe:11} {v/1e9:13.3f} {'none':>18} {'-':>7}  NO_FIG  {os.path.basename(raw)}")
            continue
        diff = abs(near - v) / v * 100
        ok = diff <= 1.0
        npass += ok
        print(f"{t:6} {pe:11} {v/1e9:13.3f} {near/1e9:18.3f} {diff:7.2f}  "
              f"{'PASS' if ok else 'FAIL':7} {os.path.basename(raw)}")
    print(f"\nwithin-1%: {npass}/{checked} checked ({len(TICKERS)} requested)")


if __name__ == "__main__":
    main()
