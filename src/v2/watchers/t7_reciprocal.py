"""
t7_reciprocal.py — watcher за T7 (reciprocal/round-trip), Фаза 4 (4.2).
======================================================================
Месечна EDGAR full-text заявка за reciprocal/round-trip език в 8-K/10-Q. Пише
КАНДИДАТИ в out/watcher_t7.md — човек преценява дали са същински reciprocal
структури; НИКАКВО автоматично сменяне на статус. Езикът е широк (шум очакван) —
затова е кандидат-списък, не сигнал.

EDGAR готчи: НЕ dateRange=custom; retry/backoff на 5xx; пауза; UA ни идентифицира.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "watcher_t7.md"
UA = {"User-Agent": "Tsachev Research tsvetoslav.tsachev@gmail.com"}
EFTS = "https://efts.sec.gov/LATEST/search-index?"

# целеви фрази (по-специфични от само "reciprocal", за да падне шумът)
PHRASES = ['"capacity swap"', '"round-trip" "capacity"', '"reciprocal" "capacity"']


def efts(params, tries=5):
    url = EFTS + urllib.parse.urlencode(params)
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if a == tries - 1:
                return {"_error": str(e)}
            time.sleep([5, 10, 15, 20][min(a, 3)])


def main(days_back=35, today=None):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # NB: today се подава (детерминизъм); ако липсва — не гадаем, ползваме фиксирана дата
    end = today or "2026-07-10"
    start = (date.fromisoformat(end) - timedelta(days=days_back)).isoformat()

    candidates, errors = [], []
    for ph in PHRASES:
        d = efts({"q": ph, "forms": "8-K,10-Q", "startdt": start, "enddt": end})
        if "_error" in d:
            errors.append((ph, d["_error"]))
            continue
        for h in d.get("hits", {}).get("hits", [])[:20]:
            s = h["_source"]
            candidates.append({"phrase": ph, "date": s.get("file_date"),
                               "form": s.get("file_type"),
                               "who": "; ".join(s.get("display_names") or [])})
        time.sleep(1.5)

    lines = ["# Watcher T7 (reciprocal/round-trip) — CANDIDATES (human confirms; no auto-status)",
             "", f"- Window: {start} .. {end} | forms 8-K,10-Q | phrases: {PHRASES}",
             f"- candidates: {len(candidates)} | errors: {len(errors)}",
             "- NOTE: broad language -> expect noise; human decides if a true reciprocal",
             "  revenue structure (sell capacity + buy back from same counterparty, quarter-end cluster).",
             ""]
    for c in candidates:
        lines.append(f"- [{c['date']}] {c['form']}  {c['who'][:80]}  (matched {c['phrase']})")
    if errors:
        lines.append("")
        for ph, e in errors:
            lines.append(f"- ERROR {ph}: {e}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[t7_reciprocal] window {start}..{end}: {len(candidates)} candidates, "
          f"{len(errors)} errors -> {OUT.name}")
    return candidates


if __name__ == "__main__":
    main()
