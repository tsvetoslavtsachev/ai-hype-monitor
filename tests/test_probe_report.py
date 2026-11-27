"""ПРОЛЕТР9, Фаза 3: мерките на пробите (приети от Ц. на 27.11.2026)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "v2"))

import probe_report as pr  # noqa: E402


def test_turns_counts_direction_changes():
    assert pr.turns([1, 2, 3, 4]) == 0
    assert pr.turns([1, 2, 1, 2]) == 2
    assert pr.turns([1, 2, 2, 1]) == 1          # плато не е смяна


def test_flat_or_price_copy_fails():
    flat = [1.0, 1.01, 1.0, 1.01, 1.0]
    v = pr.verdict(flat, 0.1)
    assert v["turns"] >= 2 and not v["moves"]    # мърда малко: размахът е под 25%
    v = pr.verdict([1, 2, 1, 2, 1], 0.9)
    assert v["moves"] and not v["not_price"] and not v["passes"]


def test_corr_sign_and_none():
    assert pr.corr([1, 2, 3], [2, 4, 6]) > 0.99
    assert pr.corr([1, 2, 3], [3, 2, 1]) < -0.99
    assert pr.corr([1, 2], [1, 2]) is None


def test_late_series_indexes_from_its_first_full_quarter():
    """Wikipedia започва през март 2023 г.: без своя база колоната беше „няма“ навсякъде (27.11.2026)."""
    qv = {"2023Q1": {"s1": 1.0, "capex": 1.0, "wiki": None},
          "2023Q2": {"s1": 1.0, "capex": 1.0, "wiki": 50.0},
          "2023Q3": {"s1": 2.0, "capex": 2.0, "wiki": 100.0}}
    rows = [r for r in pr.with_without(qv, [("Wikipedia", "wiki")]) if r.startswith("| 2023Q3")]
    assert rows and rows[0].split("|")[3].strip() == "200.0" and rows[0].split("|")[4].strip() == "200.0"
