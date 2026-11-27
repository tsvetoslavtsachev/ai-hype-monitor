"""ПРОЛЕТР9: публичната страница с двете стрелки (решение на Ц. „Публичен сайт“, 27.11.2026)."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "v2"))

import strelki_site as site  # noqa: E402

SAT = "2026-11-21"


def _o():
    return json.loads((site.WEEKLY / f"{SAT}.json").read_text(encoding="utf-8"))


def test_page_shows_the_saturday_numbers_and_dates():
    o = _o()
    page = site.render(o, site.read_series(site.WEEKLY / site.SERIES))
    assert f">{round(o['market']['level'])}<" in page and f">{round(o['history']['level'])}<" in page
    assert "20.11.2026" in page and "19.05.2023" in page
    assert o["history"]["components"] in page


def test_page_carries_no_machine_paths_addresses_or_zones():
    page = site.render(_o(), site.read_series(site.WEEKLY / site.SERIES))
    assert not re.search(r"[A-Za-z]:\\|app/data|@[A-Za-z0-9-]+\.", page)
    assert "зона" not in page.lower()


def test_chart_data_is_the_series_file():
    rows = site.read_series(site.WEEKLY / site.SERIES)
    page = site.render(_o(), rows)
    d = json.loads(re.search(r"const D=(\{.*?\});", page).group(1))
    assert d["d"][0] == "2023-05-19" and d["d"][-1] == rows[-1]["friday"]
    assert d["m"][-1] == round(float(rows[-1]["market"]), 1)


def test_main_writes_page_and_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["strelki_site.py", SAT, "--out-dir", str(tmp_path)])
    site.main()
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "data" / site.SERIES).read_bytes() == (site.WEEKLY / site.SERIES).read_bytes()


def test_refuses_series_from_another_week(tmp_path, monkeypatch):
    o = _o()
    o["friday"] = "2026-11-27"
    wk = tmp_path / "weekly"
    wk.mkdir()
    (wk / f"{SAT}.json").write_text(json.dumps(o), encoding="utf-8")
    (wk / site.SERIES).write_bytes((site.WEEKLY / site.SERIES).read_bytes())
    monkeypatch.setattr(site, "WEEKLY", wk)
    monkeypatch.setattr(sys, "argv", ["strelki_site.py", SAT, "--out-dir", str(tmp_path / "out")])
    with pytest.raises(SystemExit):
        site.main()
