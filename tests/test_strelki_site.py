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


def _ps():
    return json.loads((site.V2 / "ps_by_ticker.json").read_text(encoding="utf-8"))


def _page():
    return site.render(_o(), site.read_series(site.WEEKLY / site.SERIES), _ps())


def _data(page):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))


def test_page_shows_the_saturday_numbers_and_dates():
    o = _o()
    page = _page()
    assert f">{round(o['market']['level'])}<" in page and f">{round(o['history']['level'])}<" in page
    assert "20.11.2026" in page and "19.05.2023" in page
    assert o["history"]["components"] in page


def test_page_carries_no_machine_paths_addresses_or_zones():
    page = _page()
    assert "__" not in re.sub(r"<script.*?</script>", "", page, flags=re.S)   # всички места са попълнени
    assert "—" not in page
    assert not re.search(r"[A-Za-z]:\\|app/data|@[A-Za-z0-9-]+\.", page)
    assert "зона" not in page.lower()


def test_chart_data_is_the_series_file():
    rows = site.read_series(site.WEEKLY / site.SERIES)
    d = _data(_page())["series"]
    assert d["d"][0] == "2023-05-19" and d["d"][-1] == rows[-1]["friday"]
    assert d["m"][-1] == round(float(rows[-1]["market"]), 1)
    assert set(d["seg"]) == {k[len("seg_ps "):] for k in rows[0] if k.startswith("seg_ps ")}


def test_names_in_page_are_the_ps_file_at_the_same_weeks():
    """Графиката на компаниите е P/S от ps_by_ticker.json в същите петъци; C3.ai носи причината."""
    data, ps = _data(_page()), _ps()
    i = ps["weeks"].index(data["friday"])
    assert data["names"]["NVDA"]["ps"][-1] == round(ps["tickers"]["NVDA"]["ps"][i], 2)
    assert data["names"]["AI"]["ps"][-1] is None and data["names"]["AI"]["missing"]
    assert len(data["names"]) == len(ps["tickers"])


def test_main_writes_page_and_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["strelki_site.py", SAT, "--out-dir", str(tmp_path)])
    site.main()
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "data" / site.SERIES).read_bytes() == (site.WEEKLY / site.SERIES).read_bytes()
    assert json.loads((tmp_path / "data" / site.LATEST).read_text(encoding="utf-8"))["friday"] == _o()["friday"]


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
