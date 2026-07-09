"""
test_phase4.py — Фаза 4 тестове (offline).
==========================================
tripwires.yaml парсва (T1-T4 fired); provenance тест (всяко число в
едностраничника се проследява до съхранен вход); watcher изходите съществуват.
Генерирани изходи -> skip ако още не са произведени.
"""

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "app" / "data" / "v2"


def test_tripwires_yaml_parses():
    tw = yaml.safe_load((V2 / "tripwires.yaml").read_text(encoding="utf-8"))
    tws = tw["tripwires"]
    assert len(tws) == 10
    ids = [t["id"] for t in tws]
    assert ids == [f"T{i}" for i in range(1, 11)]
    fired = {t["id"] for t in tws if t["status"] == "fired"}
    assert fired == {"T1", "T2", "T3", "T4"}
    for t in tws:
        assert t["status"] in ("fired", "not_fired")
        for k in ("name", "definition", "source", "bearish", "bullish"):
            assert t.get(k)


def _last_defined(series, key):
    for r in reversed(series):
        if r.get(key) is not None:
            return r
    return None


def _parse_provenance(md_text):
    """Извлича {metric: value_str} от provenance таблицата."""
    out = {}
    in_tbl = False
    for ln in md_text.splitlines():
        if ln.startswith("## Provenance"):
            in_tbl = True
            continue
        if in_tbl and ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("metric", "---"):
                out[cells[0]] = cells[1]
    return out


def test_onepager_provenance_traces_to_stored_inputs():
    weekly = sorted((ROOT / "out" / "weekly").glob("*.md")) if (ROOT / "out" / "weekly").exists() else []
    if not weekly:
        pytest.skip("one-pager not generated yet")
    prov = _parse_provenance(weekly[-1].read_text(encoding="utf-8"))
    assert prov, "provenance table empty"

    gap = json.loads((V2 / "gap_series.json").read_text(encoding="utf-8"))
    zones = json.loads((V2 / "zones_retro.json").read_text(encoding="utf-8"))
    euph = json.loads((V2 / "euphoria_series.json").read_text(encoding="utf-8"))["series"]
    froth = json.loads((V2 / "froth.json").read_text(encoding="utf-8"))
    grow = _last_defined(gap["series"], "G_z")
    wk = grow["date"]
    erow = next(r for r in euph if r["date"] == wk)
    zrow = next(s for s in zones["series"] if s["date"] == wk)
    fq = _last_defined(gap["f_quarterly"], "F")

    def close(a, b):
        return abs(float(a) - float(b)) < 5e-4

    # всяко ключово число в изхода == съхранения вход
    assert close(prov["G_z"], grow["G_z"])
    assert close(prov["dG4"], grow["dG4"])
    assert close(prov["G_raw"], grow["G_raw"])
    assert prov["zone"] == zrow["committed_zone"]
    assert close(prov["z_multiple"], erow["z_multiple"])
    assert close(prov["z_promise_delivery"], erow["z_promise_delivery"])
    assert close(prov["E"], erow["E"])
    assert close(prov["F"], fq["F"])
    assert close(prov["froth_share"], froth["series"][-1]["share"])


def test_watcher_outputs():
    out = ROOT / "out"
    for name, marker in [("watcher_t9.md", "Watcher T9"), ("watcher_t10.md", "Watcher T10")]:
        p = out / name
        if not p.exists():
            pytest.skip(f"{name} not generated yet")
        assert marker in p.read_text(encoding="utf-8")
