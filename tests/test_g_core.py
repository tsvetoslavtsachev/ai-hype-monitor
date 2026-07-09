"""
test_g_core.py — Фаза 3 G-ядро тестове (offline).
=================================================
Константи от signoff, зонова машина (nominal/hysteresis), None-propagation,
етикети. Данно-зависимите тестове се пропускат ако серията още не е генерирана
(pre-registration: код+тестове = комит №1; данните = комит №2).
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "v2"))

import zones as Z  # noqa: E402

SIGNOFF = ROOT / "config" / "v2" / "zones_signoff.json"
V2 = ROOT / "app" / "data" / "v2"
CFG = json.loads(SIGNOFF.read_text(encoding="utf-8"))


# ── константи ───────────────────────────────────────────────────────────────

def test_signoff_constants_present():
    z = CFG["zones"]
    assert z["ladder"] == {"a": 1.0, "b": 2.0}
    assert z["hysteresis"] == 0.25 and z["dwell_weeks"] == 2
    assert CFG["velocity"]["flag_threshold_z"] == 1.25
    for k in ("F1", "F2", "F3"):
        assert k in CFG["falsifiers"]
    assert abs(sum(CFG["weights"]["layer_weights"].values()) - 1.0) < 1e-9
    assert CFG["f_leg_composition"]["components"] == ["revenue_growth_yoy", "operating_margin"]


# ── зонова машина (чисти функции) ───────────────────────────────────────────

def test_nominal_ladder():
    assert Z.nominal(2.5, 1.0, 2.0) == 4
    assert Z.nominal(1.5, 1.0, 2.0) == 3
    assert Z.nominal(0.0, 1.0, 2.0) == 2
    assert Z.nominal(-1.5, 1.0, 2.0) == 1
    assert Z.nominal(-2.5, 1.0, 2.0) == 0


def test_hysteresis_sticky_boundary():
    a, b, h = 1.0, 2.0, 0.25
    # от neutral: 1.10 (в мъртвата лента) остава neutral; 1.30 минава в mild_high
    assert Z.target_zone(1.10, 2, a, b, h) == 2
    assert Z.target_zone(1.30, 2, a, b, h) == 3
    # от mild_high: 0.90 (над exit прага 0.75) остава; 0.70 се връща в neutral
    assert Z.target_zone(0.90, 3, a, b, h) == 3
    assert Z.target_zone(0.70, 3, a, b, h) == 2
    # симетрично надолу
    assert Z.target_zone(-1.10, 2, a, b, h) == 2
    assert Z.target_zone(-1.30, 2, a, b, h) == 1


# ── данно-зависими (skip ако не е генерирано) ───────────────────────────────

def _load(name):
    p = V2 / name
    if not p.exists():
        pytest.skip(f"{name} not generated yet (pre-registration commit order)")
    return json.loads(p.read_text(encoding="utf-8"))


def test_gap_labeled_and_none_propagation():
    g = _load("gap_series.json")
    assert g["series_type"] == "retrospective/descriptive"
    for r in g["series"]:
        # G_z е None точно когато G_raw е None (E или F липсва) — никакъв тих 0
        if r["G_raw"] is None:
            assert r["G_z"] is None
        # F композит: None или число (мин 2 компонента)
    # F_z: където и двата компонентни z липсват -> F None
    for fr in g["f_quarterly"]:
        zs = [fr.get("z_revenue_growth_yoy"), fr.get("z_operating_margin")]
        if sum(x is not None for x in zs) < CFG["weights"]["min_components_F"]:
            assert fr["F"] is None


def test_zones_retro_labeled_and_flag():
    zr = _load("zones_retro.json")
    assert zr["series_type"] == "retrospective/descriptive"
    valid = set(Z.ZKEYS) | {"undefined", None}
    for s in zr["series"]:
        assert s["committed_zone"] in valid
        # velocity flag = |dG4| >= 1.25
        if s["dG4"] is not None:
            assert s["velocity_flag"] == (abs(s["dG4"]) >= 1.25)


def test_zone_journal_live_start():
    j = _load("zone_journal.json")
    assert j["live_start_date"] == "2026-07-10"
    assert j["entries"] == []          # живите преходи започват празни


def test_falsifier_report_generated():
    p = ROOT / "out" / "falsifier_report.md"
    if not p.exists():
        pytest.skip("falsifier_report not generated yet")
    txt = p.read_text(encoding="utf-8")
    for k in ("F1", "F2", "F3"):
        assert k in txt
