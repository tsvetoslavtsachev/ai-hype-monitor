"""
rhetoric_v2.py — Е-крак глас 1: реторичен интензитет (Фаза 2, 2.1).
==================================================================
ai_density per документ (лексиконът config/keywords.json:ai_hype_terms, методът
на v1 — брой съвпадения на 1000 думи, word-boundary за къси термини) върху
ЧИСТИЯ raw корпус. Агрегация: per (тикер, КАЛЕНДАРНО тримесечие на подаване) →
средно; после МЕДИАНА по вселената per тримесечие → робастен z (разширяващ се
прозорец, min 8 тримесечия, иначе None). Изход: app/data/v2/rhetoric_series.json.

Ретроспективна/descriptive серия. Без timestamp (детерминизъм). None ≠ 0.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from series_util import (  # noqa: E402
    calendar_quarter, quarter_end_date, quarter_sort_key,
    expanding_robust_z, _median,
)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "app" / "data" / "corpus" / "raw"
KEYWORDS = ROOT / "config" / "keywords.json"
OUT = ROOT / "app" / "data" / "v2" / "rhetoric_series.json"

_WORD = re.compile(r"\b\w+\b")


def _build_patterns(terms):
    """v1 метод: \\b за термини ≤3 знака, иначе суров escape; case-insensitive."""
    pats = []
    for t in terms:
        esc = re.escape(t)
        pats.append(re.compile((r"\b" + esc + r"\b") if len(t) <= 3 else esc, re.IGNORECASE))
    return pats


def ai_density(text: str, patterns) -> float:
    wc = len(_WORD.findall(text))
    if wc == 0:
        return None
    total = sum(len(p.findall(text)) for p in patterns)
    return total / wc * 1000.0


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    terms = json.loads(KEYWORDS.read_text(encoding="utf-8"))["ai_hype_terms"]
    patterns = _build_patterns(terms)

    # per (ticker, quarter) -> списък от плътности
    tq = {}
    for f in sorted(glob.glob(str(RAW / "*.txt"))):
        base = Path(f).name
        ticker = base.split("__")[0]
        filing_date = base.split("__")[2].replace(".txt", "")
        q = calendar_quarter(filing_date)
        d = ai_density(Path(f).read_text(encoding="utf-8", errors="ignore"), patterns)
        if d is None:
            continue
        tq.setdefault((ticker, q), []).append(d)

    # per (ticker, quarter) средно -> per quarter медиана по вселената (компании)
    quarters = sorted({q for (_, q) in tq}, key=quarter_sort_key)
    rows = []
    for q in quarters:
        # средните per тикер за това тримесечие -> медиана по вселената
        vals = []
        tickers = set()
        for (t, qq), v in tq.items():
            if qq == q:
                vals.append(sum(v) / len(v))
                tickers.add(t)
        rows.append({
            "quarter": q,
            "quarter_end": quarter_end_date(q),
            "n_tickers": len(tickers),
            "n_docs": sum(len(v) for (t, qq), v in tq.items() if qq == q),
            "median_density": round(_median(vals), 4),
        })

    zs = expanding_robust_z([r["median_density"] for r in rows], min_history=8)
    for r, z in zip(rows, zs):
        r["z"] = round(z, 4) if z is not None else None

    out = {
        "series_type": "retrospective/descriptive",
        "voice": "rhetoric_intensity",
        "lexicon_source": "config/keywords.json:ai_hype_terms",
        "method": ("ai_density (per-1000-words, word-boundary for short terms) per doc "
                   "-> per-(ticker,calendar-quarter) mean -> universe median per quarter "
                   "-> expanding robust z (median/MAD, min 8 quarters)"),
        "min_history_quarters": 8,
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== rhetoric_v2 (voice 1) ===")
    print(f"{'quarter':8} {'n_tick':>6} {'n_doc':>6} {'median_density':>15} {'z':>8}")
    for r in rows:
        z = "None" if r["z"] is None else f"{r['z']:.3f}"
        print(f"{r['quarter']:8} {r['n_tickers']:>6} {r['n_docs']:>6} "
              f"{r['median_density']:>15.4f} {z:>8}")


if __name__ == "__main__":
    main()
