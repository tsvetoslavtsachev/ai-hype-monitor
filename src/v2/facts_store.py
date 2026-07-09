"""
facts_store.py — PIT loader за F-крак фактите (Фаза 1).
======================================================
Чете app/data/v2/facts/{TICKER}.json (bitemporal) и връща стойности по
Point-In-Time правилото: НИКОГА не издава запис, чиято known_at (filed дата)
е след as_of_date. Резолюцията между fallback тагове е по приоритета от
concepts.CONCEPT_CHAINS; между винтиджи — най-скорошният known_at ≤ as_of.

Датите са ISO низове (YYYY-MM-DD) и се сравняват лексикографски (коректно).
"""

import json
from pathlib import Path

try:  # работи и като модул (src.v2), и standalone
    from concepts import tag_priority
except ImportError:  # pragma: no cover
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from concepts import tag_priority

FACTS_DIR = Path(__file__).resolve().parents[2] / "app" / "data" / "v2" / "facts"


def _facts_path(ticker: str) -> Path:
    return FACTS_DIR / f"{ticker}.json"


def load(ticker: str) -> dict:
    """Целият facts обект за тикера ({} ако липсва)."""
    p = _facts_path(ticker)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def records(ticker: str, concept: str = None) -> list:
    facts = load(ticker).get("facts", [])
    if concept is not None:
        facts = [r for r in facts if r["concept"] == concept]
    return facts


def _best_vintage(recs: list) -> dict:
    """Най-скорошен known_at; при равен known_at — най-приоритетен таг."""
    return sorted(
        recs,
        key=lambda r: (r["known_at"], -tag_priority(r["concept"], r["xbrl_tag"])),
    )[-1]


def get_asof(ticker: str, concept: str, as_of_date: str):
    """Последната (най-скорошен период) стойност, ИЗВЕСТНА към as_of_date.

    PIT: филтрира known_at ≤ as_of_date; после най-скорошният period_end,
    най-скорошният винтидж, най-приоритетният таг. Връща записа или None.
    """
    recs = [r for r in records(ticker, concept) if r["known_at"] <= as_of_date]
    if not recs:
        return None
    latest_pe = max(r["period_end"] for r in recs)
    return _best_vintage([r for r in recs if r["period_end"] == latest_pe])


def get_series_asof(ticker: str, concept: str, as_of_date: str) -> dict:
    """{period_end: value} по PIT — по един (най-добър винтидж) на период."""
    recs = [r for r in records(ticker, concept) if r["known_at"] <= as_of_date]
    by_period = {}
    for r in recs:
        by_period.setdefault(r["period_end"], []).append(r)
    return {pe: _best_vintage(rs)["value"] for pe, rs in sorted(by_period.items())}


def latest(ticker: str, concept: str):
    """Най-скорошната known стойност изобщо (as_of = безкрайно бъдеще)."""
    return get_asof(ticker, concept, "9999-12-31")
