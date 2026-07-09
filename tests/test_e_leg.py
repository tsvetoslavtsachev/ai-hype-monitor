"""
test_e_leg.py — Фаза 2 Е-крак тестове (offline, върху committed серии).
======================================================================
None-propagation за всеки глас (недостатъчна история/данни → None, никога тих 0),
етикет retrospective/descriptive, froth share ≤ 1.0, композитът E=None при <2
налични компонента.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "app" / "data" / "v2"


def _load(name):
    return json.loads((V2 / name).read_text(encoding="utf-8"))


FILES = ["rhetoric_series.json", "promise_delivery.json", "froth.json",
         "multiple_v2.json", "euphoria_series.json"]


@pytest.mark.parametrize("name", FILES)
def test_series_labeled_retrospective(name):
    obj = _load(name)
    assert obj.get("series_type") == "retrospective/descriptive"
    assert obj.get("series"), f"{name} празна серия"


@pytest.mark.parametrize("name,minh", [
    ("rhetoric_series.json", 8), ("promise_delivery.json", 8), ("froth.json", 8)])
def test_quarterly_z_none_before_min_history(name, minh):
    """Първите (min_history-1) тримесечия имат z=None; после дефиниран (null, не 0)."""
    s = _load(name)["series"]
    for r in s[:minh - 1]:
        assert r["z"] is None, f"{name} {r['quarter']} z трябва да е None"
    # поне едно дефинирано след прага
    assert any(r["z"] is not None for r in s[minh - 1:])


def test_multiple_z_none_before_min_weeks():
    obj = _load("multiple_v2.json")
    minw = obj["min_history_weeks"]
    s = obj["series"]
    for r in s[:minw - 1]:
        assert r["z"] is None
    # median_ps None => z None (без тих 0)
    for r in s:
        if r["median_ps"] is None:
            assert r["z"] is None


def test_froth_share_bounded():
    for r in _load("froth.json")["series"]:
        if r["share"] is not None:
            assert 0.0 <= r["share"] <= 1.0, f"froth share извън [0,1]: {r}"


def test_euphoria_none_iff_few_components():
    """E е None ТОЧНО когато наличните компоненти са < 2 (никакъв тих 0)."""
    for r in _load("euphoria_series.json")["series"]:
        if r["n_components"] < 2:
            assert r["E"] is None
        else:
            assert r["E"] is not None


def test_euphoria_component_count_matches():
    """n_components = броят не-None компонентни z-та."""
    comps = ["z_rhetoric", "z_promise_delivery", "z_froth", "z_multiple"]
    for r in _load("euphoria_series.json")["series"]:
        assert r["n_components"] == sum(r[c] is not None for c in comps)
