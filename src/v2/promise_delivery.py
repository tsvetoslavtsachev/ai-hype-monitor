"""
promise_delivery.py — Е-крак глас 2: обещание/доставка (Фаза 2, 2.2).
=====================================================================
promise_share = P/(P+D) per КАЛЕНДАРНО тримесечие на подаване, върху ЧИСТИЯ raw
корпус. Лексиконите: config/v2/lexicons.json (v1 = c3 база + консервативни
разширения). Метод (както v0/C3): substring, case-insensitive, pooled per
тримесечие: P_1k = сума промис-съвпадения / сума думи · 1000 (аналогично D_1k);
share = P/(P+D). После робастен z (разширяващ се, min 8). Изход:
app/data/v2/promise_delivery.json. Ретроспективна/descriptive. None ≠ 0.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from series_util import (  # noqa: E402
    calendar_quarter, quarter_end_date, quarter_sort_key, expanding_robust_z,
)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "app" / "data" / "corpus" / "raw"
LEXICONS = ROOT / "config" / "v2" / "lexicons.json"
OUT = ROOT / "app" / "data" / "v2" / "promise_delivery.json"

_WORD = re.compile(r"\b\w+\b")


def _count(text_lower: str, terms) -> int:
    return sum(text_lower.count(t) for t in terms)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lex = json.loads(LEXICONS.read_text(encoding="utf-8"))
    promise, delivery = lex["promise"], lex["delivery"]

    # pooled per тримесечие: сума промис/доставка съвпадения + сума думи
    agg = {}  # q -> [p_hits, d_hits, words, n_docs]
    for f in sorted(glob.glob(str(RAW / "*.txt"))):
        base = Path(f).name
        q = calendar_quarter(base.split("__")[2].replace(".txt", ""))
        text = Path(f).read_text(encoding="utf-8", errors="ignore")
        tl = text.lower()
        wc = len(_WORD.findall(text))
        if wc == 0:
            continue
        a = agg.setdefault(q, [0, 0, 0, 0])
        a[0] += _count(tl, promise)
        a[1] += _count(tl, delivery)
        a[2] += wc
        a[3] += 1

    rows = []
    for q in sorted(agg, key=quarter_sort_key):
        p_hits, d_hits, words, n = agg[q]
        p_1k = p_hits / words * 1000
        d_1k = d_hits / words * 1000
        share = p_1k / (p_1k + d_1k) if (p_1k + d_1k) > 0 else None
        rows.append({
            "quarter": q, "quarter_end": quarter_end_date(q), "n_docs": n,
            "promise_1k": round(p_1k, 4), "delivery_1k": round(d_1k, 4),
            "promise_share": round(share, 4) if share is not None else None,
        })

    zs = expanding_robust_z([r["promise_share"] for r in rows], min_history=8)
    for r, z in zip(rows, zs):
        r["z"] = round(z, 4) if z is not None else None

    out = {
        "series_type": "retrospective/descriptive",
        "voice": "promise_delivery",
        "lexicon_source": "config/v2/lexicons.json (v1)",
        "method": ("substring match, pooled per calendar quarter: P_1k, D_1k "
                   "(per-1000-words) -> promise_share = P/(P+D) -> expanding robust z "
                   "(median/MAD, min 8 quarters)"),
        "min_history_quarters": 8,
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== promise_delivery (voice 2) ===")
    print(f"{'quarter':8} {'n_doc':>6} {'P_1k':>7} {'D_1k':>7} {'share':>7} {'z':>8}")
    for r in rows:
        z = "None" if r["z"] is None else f"{r['z']:.3f}"
        print(f"{r['quarter']:8} {r['n_docs']:>6} {r['promise_1k']:>7.3f} "
              f"{r['delivery_1k']:>7.3f} {r['promise_share']:>7.3f} {z:>8}")


if __name__ == "__main__":
    main()
