"""
froth.py — Е-крак глас 4: пяна по ръбовете (Фаза 2, 2.4).
=========================================================
Продукционизира probe_c4b_froth_normalized.py: делът на S-1-root проспекти
(S-1 + S-1/A), които съдържат точната фраза "artificial intelligence", per
КАЛЕНДАРНО тримесечие 2023Q1..сега, + tech/non-tech SIC разбивка за последното
тримесечие. После робастен z (разширяващ се, min 8 тримесечия).

Числител: EDGAR full-text search (efts) total per тримесечие (S-1 root).
Знаменател: form.idx (exact S-1 + S-1/A, first-token match). Кеш в
app/data/v2/froth_cache/ (детерминизъм + без повторно теглене).
Изход: app/data/v2/froth.json. Ретроспективна/descriptive. None ≠ 0.

EDGAR готчи (доказани): НЕ пращай dateRange=custom (HTTP 500); retry/backoff
на спорадични 5xx; ~1.5s пауза; UA ни идентифицира.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from series_util import expanding_robust_z, quarter_sort_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "data" / "v2" / "froth.json"
CACHE = ROOT / "app" / "data" / "v2" / "froth_cache"

UA = {"User-Agent": "Tsachev Research tsvetoslav.tsachev@gmail.com"}
EFTS = "https://efts.sec.gov/LATEST/search-index?"

# тримесечия 2023Q1 .. текущо (спрямо днешната дата се спира; тук до 2026Q2)
def quarters_upto(y_end, q_end):
    out = []
    for y in range(2023, y_end + 1):
        for qn in range(1, 5):
            if (y, qn) > (y_end, q_end):
                continue
            out.append((f"{y}Q{qn}", y, qn))
    return out


QRANGE = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"),
          3: ("07-01", "09-30"), 4: ("10-01", "12-31")}


def _get(url, tries=5):
    last = None
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as ex:
            last = ex
            if a == tries - 1:
                raise
            time.sleep([5, 10, 15, 20][min(a, 3)])
    raise last


def efts(params):
    return json.loads(_get(EFTS + urllib.parse.urlencode(params)).decode())


def fts_total(y, qn):
    """Брой S-1-root документи с фразата за тримесечието (efts total)."""
    ck = CACHE / f"fts_{y}Q{qn}.json"
    if ck.exists():
        return json.loads(ck.read_text(encoding="utf-8"))["total"]
    s, e = QRANGE[qn]
    d = efts({"q": '"artificial intelligence"', "forms": "S-1",
              "startdt": f"{y}-{s}", "enddt": f"{y}-{e}"})
    total = d["hits"]["total"]["value"]
    ck.write_text(json.dumps({"total": total}), encoding="utf-8")
    time.sleep(1.5)
    return total


def form_idx_counts(y, qn):
    """S-1 + S-1/A от form.idx (first-token match). Кеширани броеве."""
    ck = CACHE / f"counts_{y}Q{qn}.json"
    if ck.exists():
        return json.loads(ck.read_text(encoding="utf-8"))
    raw = _get(f"https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{qn}/form.idx").decode("latin-1")
    c = Counter()
    for ln in raw.splitlines():
        parts = ln.split()
        if parts:
            c[parts[0]] += 1
    out = {"s1": c.get("S-1", 0), "s1a": c.get("S-1/A", 0), "s1mef": c.get("S-1MEF", 0)}
    ck.write_text(json.dumps(out), encoding="utf-8")
    time.sleep(0.5)
    return out


def is_tech(sic):
    try:
        n = int(sic)
    except (TypeError, ValueError):
        return None
    return (3570 <= n <= 3579) or (3660 <= n <= 3699) or (7370 <= n <= 7379)


def sic_split(y, qn):
    """tech/non-tech по уникални CIK за тримесечието (efts _source.sics)."""
    s, e = QRANGE[qn]
    base = {"q": '"artificial intelligence"', "forms": "S-1",
            "startdt": f"{y}-{s}", "enddt": f"{y}-{e}"}
    first = efts(base)
    total = first["hits"]["total"]["value"]
    hits = list(first["hits"]["hits"])
    time.sleep(1.5)
    while len(hits) < total:
        p = dict(base); p["from"] = len(hits)
        page = efts(p)["hits"]["hits"]
        if not page:
            break
        hits += page
        time.sleep(1.5)
    cik_sic = {}
    for h in hits:
        sics = h["_source"].get("sics") or []
        for c in h["_source"].get("ciks", []):
            if c not in cik_sic and sics:
                cik_sic[c] = sics[0]
    ciks = {c for h in hits for c in h["_source"].get("ciks", [])}
    tech = sum(1 for c in ciks if is_tech(cik_sic.get(c)) is True)
    nontech = sum(1 for c in ciks if is_tech(cik_sic.get(c)) is False)
    unknown = sum(1 for c in ciks if is_tech(cik_sic.get(c)) is None)
    n_cls = tech + nontech
    return {"unique_ciks": len(ciks), "tech": tech, "nontech": nontech,
            "unknown_sic": unknown,
            "nontech_share_pct": round(100 * nontech / n_cls, 1) if n_cls else None}


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    today = date.today()
    y_end, q_end = today.year, (today.month - 1) // 3 + 1
    # включваме само ПРИКЛЮЧИЛИ тримесечия (текущото още не е пълно)
    q_end -= 1
    if q_end == 0:
        y_end, q_end = y_end - 1, 4
    quarters = quarters_upto(y_end, q_end)

    rows = []
    for label, y, qn in quarters:
        num = fts_total(y, qn)
        den = form_idx_counts(y, qn)
        root = den["s1"] + den["s1a"]
        share = num / root if root else None
        rows.append({"quarter": label, "ai_hits": num, "s1_root_filings": root,
                     "share": round(share, 4) if share is not None else None,
                     "share_pct": round(100 * share, 1) if share is not None else None})

    zs = expanding_robust_z([r["share"] for r in rows], min_history=8)
    for r, z in zip(rows, zs):
        r["z"] = round(z, 4) if z is not None else None

    latest = quarters[-1]
    split = sic_split(latest[1], latest[2])

    out = {
        "series_type": "retrospective/descriptive",
        "voice": "froth",
        "method": ("share of S-1-root filings (S-1+S-1/A) containing 'artificial "
                   "intelligence' per calendar quarter -> expanding robust z (min 8). "
                   "Numerator: efts total (documents; mild overcount). Denominator: "
                   "form.idx S-1+S-1/A. Phrase-mention != AI-centrality."),
        "min_history_quarters": 8,
        "latest_quarter_sic_split": {"quarter": latest[0], **split},
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== froth (voice 4) ===")
    print(f"{'quarter':8} {'ai_hits':>7} {'s1_root':>7} {'share%':>7} {'z':>8}")
    for r in rows:
        z = "None" if r["z"] is None else f"{r['z']:.3f}"
        print(f"{r['quarter']:8} {r['ai_hits']:>7} {r['s1_root_filings']:>7} "
              f"{r['share_pct']:>7} {z:>8}")
    print(f"latest SIC split ({latest[0]}): {split}")


if __name__ == "__main__":
    main()
