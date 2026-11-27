"""ПРОЛЕТР9, Фаза 2: резервите за броя акции и капекса, TTM от натрупаните отчети."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "v2"))

import collect_xbrl as cx  # noqa: E402
import facts_store as fs  # noqa: E402


def _rec(concept, tag, start, end, value, known):
    return {"concept": concept, "xbrl_tag": tag, "period_start": start, "period_end": end,
            "value": value, "unit": "x", "form": "10-Q", "known_at": known, "accn": known}


def _with(monkeypatch, recs):
    monkeypatch.setattr(fs, "load", lambda t: {"facts": recs})


DEI = "dei:EntityCommonStockSharesOutstanding"
CSO = "us-gaap:CommonStockSharesOutstanding"
WAD = "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding"


def test_shares_dei_wins_when_fresh_even_if_balance_count_is_later(monkeypatch):
    _with(monkeypatch, [_rec("shares", DEI, "2026-07-20", "2026-07-20", 100, "2026-07-30"),
                        _rec("shares", CSO, "2026-09-30", "2026-09-30", 90, "2026-10-30")])
    r = fs.get_asof("X", "shares", "2026-11-20")
    assert r["xbrl_tag"] == DEI and r["value"] == 100


def test_shares_fallback_when_no_dei(monkeypatch):
    _with(monkeypatch, [_rec("shares", CSO, "2026-09-30", "2026-09-30", 90, "2026-10-30")])
    assert fs.get_asof("X", "shares", "2026-11-20")["value"] == 90


def test_stale_dei_does_not_hold_the_name(monkeypatch):
    _with(monkeypatch, [_rec("shares", DEI, "2024-01-20", "2024-01-20", 100, "2024-01-30"),
                        _rec("shares", CSO, "2026-09-30", "2026-09-30", 90, "2026-10-30")])
    r = fs.get_asof("X", "shares", "2026-11-20")
    assert r["xbrl_tag"] == CSO


def test_shares_pit_not_before_filed(monkeypatch):
    _with(monkeypatch, [_rec("shares", CSO, "2026-09-30", "2026-09-30", 90, "2026-10-30")])
    assert fs.get_asof("X", "shares", "2026-10-29") is None


def test_weighted_average_only_quarterly_as_point():
    cf = {"facts": {"us-gaap": {"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
        {"start": "2026-07-01", "end": "2026-09-30", "val": 5, "filed": "2026-10-30", "accn": "a"},
        {"start": "2026-01-01", "end": "2026-09-30", "val": 6, "filed": "2026-10-30", "accn": "a"},
    ]}}}}}
    recs = [r for r in cx.extract_records(cf) if r["concept"] == "shares"]
    assert len(recs) == 1
    assert recs[0]["value"] == 5 and recs[0]["period_start"] == recs[0]["period_end"] == "2026-09-30"


def test_capex_productive_assets_fallback():
    cf = {"facts": {"us-gaap": {"PaymentsToAcquireProductiveAssets": {"units": {"USD": [
        {"start": "2026-07-01", "end": "2026-09-30", "val": 77, "filed": "2026-10-30", "accn": "a"},
    ]}}}}}
    recs = [r for r in cx.extract_records(cf) if r["concept"] == "capex"]
    assert [r["value"] for r in recs] == [77]


def test_ttm_uses_latest_ytd_not_only_quarters(monkeypatch):
    """Капекс само с натрупано (GOOGL, META): TTM е към 9M, не към Q1."""
    C = "capex"
    T = "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"
    _with(monkeypatch, [
        _rec(C, T, "2025-01-01", "2025-12-31", 100, "2026-02-05"),   # FY 2025
        _rec(C, T, "2025-01-01", "2025-09-30", 70, "2025-10-30"),    # 9M 2025
        _rec(C, T, "2026-01-01", "2026-03-31", 30, "2026-04-30"),    # Q1 2026
        _rec(C, T, "2026-01-01", "2026-09-30", 110, "2026-10-29"),   # 9M 2026
    ])
    r = fs.ttm_asof("X", C, "2026-11-20")
    assert r["value"] == 100 + 110 - 70
    assert max(c["period_end"] for c in r["derived_from"]) == "2026-09-30"


def test_ttm_takes_fy_after_10k(monkeypatch):
    """След годишния отчет TTM е годината, не третото тримесечие (стария бъг)."""
    C = "revenue"
    T = "us-gaap:Revenues"
    _with(monkeypatch, [
        _rec(C, T, "2025-07-01", "2025-09-30", 30, "2025-10-30"),
        _rec(C, T, "2025-04-01", "2025-06-30", 25, "2025-07-30"),
        _rec(C, T, "2025-01-01", "2025-03-31", 20, "2025-04-30"),
        _rec(C, T, "2024-10-01", "2024-12-31", 15, "2025-02-05"),
        _rec(C, T, "2025-01-01", "2025-12-31", 110, "2026-02-05"),
    ])
    assert fs.ttm_asof("X", C, "2026-01-15")["value"] == 90
    assert fs.ttm_asof("X", C, "2026-03-13")["value"] == 110


def test_ttm_identity_tries_every_ytd_candidate(monkeypatch):
    """ONTO след смяната на календара: два 9M с край 30.09; само единият стъпва на FY."""
    C, T = "revenue", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    _with(monkeypatch, [
        _rec(C, T, "2024-12-29", "2026-01-03", 1005, "2026-02-24"),   # FY 2025 (53 седмици)
        _rec(C, T, "2024-12-29", "2025-09-27", 738, "2025-11-05"),    # 9M 2025
        _rec(C, T, "2026-01-04", "2026-03-31", 292, "2026-05-05"),
        _rec(C, T, "2026-04-01", "2026-06-30", 343, "2026-08-06"),
        _rec(C, T, "2026-07-01", "2026-09-30", 410, "2026-11-09"),
        _rec(C, T, "2026-01-01", "2026-09-30", 1045, "2026-11-09"),   # 9M, начало 01.01
        _rec(C, T, "2026-01-04", "2026-09-30", 1045, "2026-11-09"),   # 9M, начало 04.01
    ])
    r = fs.ttm_asof("X", C, "2026-11-20")
    assert r is not None and r["value"] == 1005 + 1045 - 738


def test_diluted_fallback_only_for_meta(monkeypatch):
    """Избор 2 на Ц.: разводнените акции са резерва само за META; AI остава вън (27.11.2026)."""
    recs = [_rec("shares", WAD, "2026-07-31", "2026-07-31", 155, "2026-09-09")]  # събирачът я пази като точка
    _with(monkeypatch, recs)
    assert fs.get_asof("AI", "shares", "2026-11-20") is None
    assert fs.get_asof("META", "shares", "2026-11-20")["value"] == 155


def test_ttm_carries_its_currency(monkeypatch):
    recs = [{**_rec("revenue", "us-gaap:Revenues", "2025-01-01", "2025-12-31", 32.7e9, "2026-02-25"), "unit": "EUR"}]
    _with(monkeypatch, recs)
    assert fs.ttm_asof("ASML", "revenue", "2026-11-20")["unit"] == "EUR"
