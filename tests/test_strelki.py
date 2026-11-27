"""ПРОЛЕТР9, Фаза 4: правилата на двете стрелки и капитализацията след сплит."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "v2"))

import multiple_v2 as m  # noqa: E402
import strelki as s  # noqa: E402


def _q(s1=None, capex=None, words=None):
    return {"s1": s1, "s1_counts": (None, None), "capex": capex, "capex_detail": None, "words": words}


QV = {"2023Q1": _q(0.25, 13.0, 0.02), "2026Q2": _q(0.5, 30.0, 0.14), "2026Q3": _q(0.6, 36.0, 0.16)}


def test_quarter_value_never_before_valid_from():
    """2026Q3 свършва на 30.09; важи от 14.11.2026, не на 13.11."""
    assert s.effective("2026Q3") == "2026-11-14"
    assert s.held(QV, "s1", "2026-11-13")[0] == "2026Q2"
    assert s.held(QV, "s1", "2026-11-14")[0] == "2026Q3"


def test_base_week_is_fixed_and_is_100():
    assert s.BASE_WEEK == "2023-05-19"
    series = [("2023-05-12", 2.0, 30), ("2023-05-19", 2.5, 30), ("2026-11-20", 7.5, 30)]
    mk = s.market_arrow(series)
    assert "2023-05-12" not in mk
    assert mk["2023-05-19"][0] == pytest.approx(100.0)
    assert mk["2026-11-20"][0] == pytest.approx(300.0)
    h = s.history_arrow(["2023-05-19"], QV)
    assert h["2023-05-19"]["index"] == pytest.approx(100.0)


def test_history_is_geometric_mean_of_component_indices():
    h = s.history_arrow(["2026-11-20"], QV)["2026-11-20"]
    expect = ((100 * 0.6 / 0.25) * (100 * 36.0 / 13.0) * (100 * 0.16 / 0.02)) ** (1 / 3)
    assert h["index"] == pytest.approx(expect)
    assert (h["n_used"], h["n_total"]) == (3, 3)
    assert [p["key"] for p in h["parts"]] == ["s1", "capex", "words"]    # „Само думите“, 27.11.2026
    assert all(p["state"] == "свежа" for p in h["parts"])


def test_missing_component_is_named_not_silently_averaged():
    qv = {k: _q(v["s1"], None, v["words"]) for k, v in QV.items()}
    h = s.history_arrow(["2026-11-20"], qv)["2026-11-20"]
    assert (h["n_used"], h["n_total"]) == (2, 3)
    miss = [p for p in h["parts"] if p["state"] == "липсва"]
    assert [p["key"] for p in miss] == ["capex"]
    assert h["index"] == pytest.approx(math.sqrt((100 * 0.6 / 0.25) * (100 * 0.16 / 0.02)))


def test_stale_component_is_named_with_its_quarter():
    qv = dict(QV)
    qv["2026Q3"] = _q(0.6, None, 0.16)    # капексът за Q3 още го няма
    h = s.history_arrow(["2026-11-20"], qv)["2026-11-20"]
    cap = [p for p in h["parts"] if p["key"] == "capex"][0]
    assert cap["state"] == "остаряла" and cap["quarter"] == "2026Q2" and cap["expected_quarter"] == "2026Q3"


def test_readings_month_year_peak():
    lv = {f"w{i:03d}": float(v) for i, v in enumerate([100] * 48 + [200, 300, 250, 260, 240, 230, 220])}
    r = s.readings(lv, "w054")
    assert r["vs_4_weeks"]["date"] == "w050" and r["vs_4_weeks"]["change_pct"] == pytest.approx(round((220 / 250 - 1) * 100, 1))
    assert r["vs_52_weeks"]["date"] == "w002"
    assert r["peak"]["date"] == "w049" and r["peak"]["distance_pct"] == pytest.approx(round((220 / 300 - 1) * 100, 1))


def test_ps_after_split_uses_shares_in_todays_basis(monkeypatch):
    """Сплит 10:1 след датата на акциите: цената е в днешната база, акциите се умножават по 10."""
    series = (["2024-01-05", "2024-06-14"], [50.0, 120.0], [10.0, 1.0])
    monkeypatch.setattr(m.fs, "get_asof", lambda t, c, d: {"value": 2.5e9, "xbrl_tag": "dei:X",
                                                           "period_end": "2023-11-17", "known_at": "2023-11-21"})
    monkeypatch.setattr(m.fs, "ttm_asof", lambda t, c, d: {"value": 50e9, "known_at": "2023-11-21", "method": "sum_4q",
                                                           "derived_from": [{"period_end": "2023-10-29"}]})
    ps, det = m.ticker_ps(series, "X", "2024-01-05")
    assert ps == pytest.approx(50.0 * 2.5e9 * 10 / 50e9)       # 25, не 2,5
    assert det["split_adj"] == 10.0


def test_md_and_block_carry_dates():
    o = {"friday": "2026-11-20", "saturday": "2026-11-21", "base_week": "2023-05-19",
         "market": {"date": "2026-11-20", "level": 288.0, "vs_4_weeks": {"change_pct": -30.0, "date": "2026-10-23"},
                    "vs_52_weeks": {"change_pct": 16.8, "date": "2025-11-21"}, "peak": {"level": 520.0, "date": "2026-05-29", "distance_pct": -44.7},
                    "median_ps": 7.7, "base_median_ps": 2.7, "n_names": 30, "source": "x"},
         "history": {"level": 250.0, "vs_4_weeks": {"change_pct": 7.6, "date": "2026-10-23"}, "vs_52_weeks": {"change_pct": 54.7, "date": "2025-11-21"},
                     "peak": {"level": 250.0, "date": "2026-11-20", "distance_pct": 0.0}, "components": "2 от 2",
                     "stale_or_missing": [], "parts": [
                         {"key": "s1", "label": "S-1", "state": "свежа", "quarter": "2026Q3", "valid_from": "2026-11-14",
                          "value": 0.58, "base_value": 0.26, "base_quarter": "2023Q1", "index": 227.0, "source": "x"}]},
         "segments": [], "names": [], "frozen": "x"}
    md = s.render_md(o)
    assert "20.11.2026" in md and "2026Q3, важи от 14.11.2026" in md and "(от 23.10.2026)" in md


def test_ps_stale_shares_is_missing_not_a_price(monkeypatch):
    """27.11.2026: AI взимаше броя акции от април 2021 г. (само клас B) и P/S 0,14."""
    series = (["2026-11-20"], [9.13], [1.0])
    monkeypatch.setattr(m.fs, "get_asof", lambda t, c, d: {"value": 3_499_992, "xbrl_tag": "us-gaap:X",
                                                           "period_end": "2021-04-30", "known_at": "2021-06-25"})
    monkeypatch.setattr(m.fs, "ttm_asof", lambda t, c, d: {"value": 232e6, "known_at": "2026-09-09", "method": "identity",
                                                           "derived_from": [{"period_end": "2026-07-31"}]})
    ps, det = m.ticker_ps(series, "AI", "2026-11-20")
    assert ps is None and "shares older than" in det["missing"]


def test_ps_annual_filer_one_year_back_still_counts(monkeypatch):
    """ASML (20-F): броят акции и продажбите към 31.12 важат до следващия годишен отчет."""
    series = (["2026-11-20"], [1266.22], [1.0])
    monkeypatch.setattr(m.fs, "get_asof", lambda t, c, d: {"value": 385e6, "xbrl_tag": "dei:X",
                                                           "period_end": "2025-12-31", "known_at": "2026-02-25"})
    monkeypatch.setattr(m.fs, "ttm_asof", lambda t, c, d: {"value": 32.7e9, "known_at": "2026-02-25", "method": "fy_only",
                                                           "derived_from": [{"period_end": "2025-12-31"}]})
    ps, _ = m.ticker_ps(series, "ASML", "2026-11-20")
    assert ps is not None


def test_words_missing_is_named_in_block_terms():
    """Без файла за думите историята казва „2 от 3“ и назовава думите (Ц., „Само думите“)."""
    qv = {k: _q(v["s1"], v["capex"], None) for k, v in QV.items()}
    h = s.history_arrow(["2026-11-20"], qv)["2026-11-20"]
    assert (h["n_used"], h["n_total"]) == (2, 3)
    assert [p["key"] for p in h["parts"] if p["state"] == "липсва"] == ["words"]
    assert s.SHORT["words"] == "AI думите в резултатите"


def test_words_quarter_is_the_filing_quarter(monkeypatch):
    monkeypatch.setattr(s, "load_json", lambda n: {"series": [{"filing_quarter": "2026Q3", "share": 0.1625},
                                                              {"filing_quarter": "2026Q4", "share": None}]})
    assert s.words_quarters() == {"2026Q3": 0.1625}
