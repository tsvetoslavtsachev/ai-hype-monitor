"""ПРОЛЕТР9, Фаза 1: идентификацията пред SEC идва само от настройката SEC_USER_AGENT."""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC / "v2"))

import sec_ua  # noqa: E402

SEC_SCRIPTS = ["v2/collect_xbrl.py", "v2/froth.py", "v2/watchers/t7_reciprocal.py",
               "backfill_edgar.py", "build_corpus.py", "fetch_sec_edgar.py"]
ADDR = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}")


def test_without_setting_stops_with_clear_error(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(SystemExit) as e:
        sec_ua.sec_headers()
    assert "SEC_USER_AGENT" in str(e.value)


def test_blank_setting_is_not_a_setting(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "   ")
    with pytest.raises(SystemExit):
        sec_ua.sec_user_agent()


def test_setting_goes_into_header(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Client test-contact")
    h = sec_ua.sec_headers({"Accept-Encoding": "gzip, deflate"})
    assert h == {"User-Agent": "Test Client test-contact", "Accept-Encoding": "gzip, deflate"}


@pytest.mark.parametrize("rel", SEC_SCRIPTS)
def test_no_address_written_in_sec_scripts(rel):
    text = (SRC / rel).read_text(encoding="utf-8")
    assert not ADDR.search(text), f"{rel}: адрес, записан в кода"
    assert "sec_headers" in text, f"{rel}: не чете заглавката от sec_ua"


def test_no_address_anywhere_under_src():
    hits = [str(p.relative_to(ROOT)) for p in SRC.rglob("*.py")
            if ADDR.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert hits == []


@pytest.mark.parametrize("rel", ["v2/collect_xbrl.py", "v2/froth.py", "v2/watchers/t7_reciprocal.py"])
def test_modules_import_without_setting(monkeypatch, rel):
    """Настройката се чете при заявката, не при импорта (тестовете и сухите ходове)."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    spec = importlib.util.spec_from_file_location("m_" + Path(rel).stem, SRC / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


def test_placeholder_or_cyrillic_stops_before_any_request(monkeypatch):
    """27.11.2026: образецът „<име> <адрес>“ на кирилица гърмеше в latin-1 при всяка заявка."""
    for bad in ["<име> <адрес>", "<name> <address>", "Иван test-contact"]:
        monkeypatch.setenv("SEC_USER_AGENT", bad)
        with pytest.raises(SystemExit):
            sec_ua.sec_user_agent()
