"""
test_facts_store.py — Фаза 1 F-крак тестове (offline, върху committed факти).
============================================================================
1. PIT инвариант: known_at ≥ period_end за ВСЕКИ запис.
2. get_asof никога не връща запис с known_at > as_of (PIT четене).
3. Идемпотентност: canonical_dump(load(file)) байт-възпроизвежда файла.
4. None-propagation: липсващ концепт → None (никога тих 0).
"""

import glob
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "v2"))

import facts_store as fs        # noqa: E402
import collect_xbrl as cx       # noqa: E402
from concepts import CONCEPT_CHAINS  # noqa: E402

FACTS_DIR = ROOT / "app" / "data" / "v2" / "facts"
FACT_FILES = sorted(glob.glob(str(FACTS_DIR / "*.json")))


def test_facts_dir_populated():
    assert len(FACT_FILES) >= 30, f"too few facts files: {len(FACT_FILES)}"


def test_pit_invariant_known_at_ge_period_end():
    """Всеки факт е станал известен НЕ преди края на периода си."""
    violations = []
    for f in FACT_FILES:
        obj = json.load(open(f, encoding="utf-8"))
        for r in obj["facts"]:
            if r["known_at"] < r["period_end"]:
                violations.append((obj["ticker"], r["concept"],
                                   r["period_end"], r["known_at"]))
    assert not violations, f"{len(violations)} PIT нарушения, напр. {violations[:5]}"


@pytest.mark.parametrize("as_of", ["2021-01-01", "2023-06-30", "2024-12-31", "9999-12-31"])
def test_get_asof_never_returns_future(as_of):
    """get_asof никога не издава запис, известен след as_of."""
    for t in ["NVDA", "MSFT", "AMD", "AMAT", "MU"]:
        for concept in CONCEPT_CHAINS:
            rec = fs.get_asof(t, concept, as_of)
            if rec is not None:
                assert rec["known_at"] <= as_of, (
                    f"{t}/{concept}@{as_of}: върна known_at={rec['known_at']}")


def test_get_asof_resolves_latest_revenue():
    """Санитарен: NVDA има последно тримесечно revenue > 0 и period ⊆ known_at."""
    rec = fs.latest("NVDA", "revenue")
    assert rec is not None
    assert rec["value"] > 0
    assert rec["known_at"] >= rec["period_end"]


def test_get_asof_boundary():
    """as_of преди първото подаване -> None; на самото подаване -> вече видимо."""
    from datetime import date, timedelta
    recs = fs.records("NVDA", "revenue")
    earliest = min(r["known_at"] for r in recs)
    before = (date.fromisoformat(earliest) - timedelta(days=1)).isoformat()
    assert fs.get_asof("NVDA", "revenue", before) is None
    rec = fs.get_asof("NVDA", "revenue", earliest)
    assert rec is not None and rec["known_at"] <= earliest


def test_idempotent_canonical_form():
    """Всеки съхранен файл е в canonical форма => повторен пуск дава 0 диф."""
    for f in FACT_FILES:
        raw = Path(f).read_text(encoding="utf-8")
        obj = json.loads(raw)
        reproduced = cx.canonical_dump(
            obj["ticker"], obj["cik"], obj["entity_name"], obj["facts"])
        assert reproduced == raw, f"{obj['ticker']} не е в canonical форма"


def test_none_propagation_missing_concept():
    """Липсващ концепт се разпространява като None, НЕ като 0."""
    # ASML (foreign, IFRS годишно) няма тримесечно revenue
    assert fs.latest("ASML", "revenue") is None
    assert fs.get_series_asof("ASML", "revenue", "9999-12-31") == {}
    # GOOGL/META не подават dei:EntityCommonStockSharesOutstanding
    assert fs.latest("GOOGL", "shares") is None
    # но налични концепти НЕ са None
    assert fs.latest("ASML", "shares") is not None
    assert fs.latest("NVDA", "revenue") is not None
