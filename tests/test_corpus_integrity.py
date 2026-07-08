"""
test_corpus_integrity.py — постоянни санитарни тестове за raw корпуса.
=====================================================================
Пази корпуса от тихо замърсяване (историческият CIK-контаминационен бъг:
AMAT файлове съдържаха Adobe прессъобщения и т.н.). Всичко е OFFLINE —
работи само върху committed данни (raw текстове + committed snapshot на
SEC company_tickers.json). Никаква мрежа.

Три групи проверки:
  1. test_own_company_name_present  — за ВСЕКИ raw файл собственото име на
     компанията присъства в първите 6000 знака (глобален чек по модела на
     probes/probe_c2b_contamination.py + probes/gate2_recheck.py).
  2. test_no_wrong_company_token    — за 5-те исторически контаминирани тикера
     съответният ГРЕШЕН токен отсъства (AMAT!=adobe, DELL!=saic, SMCI!=stryker,
     PWR!=salem media, LITE!=axalta). Per-ticker по дизайн: „adobe"/„saic" се
     срещат ЛЕГИТИМНО в чужди отчети (AMZN/ORCL споменават партньори), затова
     глобален wrong-token чек би дал фалшиви позитиви — виж gate2_recheck.py.
  3. test_universe_cik_matches_snapshot — CIK-овете в universe.csv съвпадат с
     авторитетния company_tickers.json snapshot (хваща CIK-дрейф като стария
     PWR->Salem Media бъг, преди да замърси корпуса).
  4. test_enabled_tickers_have_corpus — всеки активен тикер има >=1 raw файл,
     освен документираните изключения (KNOWN_MISSING).
"""

import csv
import glob
import json
import os
from pathlib import Path

import pytest

# ── Пътища (offline; всичко committed) ─────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "app" / "data" / "corpus" / "raw"
UNIVERSE = ROOT / "config" / "universe.csv"
# committed snapshot на SEC company_tickers.json (с дата в името)
CIK_SNAPSHOT = ROOT / "tests" / "fixtures" / "company_tickers_2026-07-08.json"

HEAD_CHARS = 6000  # прозорец за проверка на собствено име (мандат 0.5)

# ── Собствено име на компанията: първа дума от universe.name, малки букви,
#    + доказани override-и (probes/gate2_recheck.py). Мултитокен за SMCI. ────
NAME_OVERRIDES = {
    "GOOGL": "google", "META": "meta", "MSFT": "microsoft", "AMZN": "amazon",
    "AI": "c3", "ARM": "arm", "NOW": "servicenow", "CRM": "salesforce",
    "SMCI": "supermicro",  # брандът е една дума „Supermicro"
    "AMD": "amd",          # „Advanced Micro Devices" boilerplate е след 6000 знака
}
OWN_MULTI = {"SMCI": ["super micro", "supermicro"]}

# 5-те исторически контаминирани тикера -> техният ГРЕШЕН токен (чужда компания)
WRONG_TOKEN = {
    "AMAT": "adobe", "DELL": "saic", "SMCI": "stryker",
    "PWR": "salem media", "LITE": "axalta",
}

# Активни тикери без raw корпус — документирани причини (не са провал):
#  - foreign filer: подава 20-F/6-K, няма 8-K item 2.02 (структурно).
#  - exhibit-matcher: има 8-K 2.02, но build_corpus.get_exhibit_text търси
#    буквално EX-99.1/EX-99.2 в индекса и не хваща етикета на този емитент
#    (Phase 2 rhetoric_v2 кандидат за поправка; backfill_edgar ги хваща).
KNOWN_MISSING = {
    "ASML": "foreign filer (20-F/6-K); no 8-K item 2.02",
    "ARM": "foreign filer (20-F/6-K); no 8-K item 2.02",
    "ETN": "8-K 2.02 present but EX-99.1/EX-99.2 exhibit not matched by build_corpus",
    "CDNS": "8-K 2.02 present but EX-99.1/EX-99.2 exhibit not matched by build_corpus",
}


def _load_universe():
    rows = {}
    with open(UNIVERSE, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("enabled", "1")).strip() not in ("1", "true", "True"):
                continue
            rows[r["symbol"].strip()] = {
                "name": r["name"].strip(),
                "cik": str(r.get("cik", "") or "").strip(),
            }
    return rows


def _name_tokens(symbol: str, uni: dict) -> list:
    """Токен(и) за собствено име на компанията."""
    if symbol in OWN_MULTI:
        return OWN_MULTI[symbol]
    if symbol in NAME_OVERRIDES:
        return [NAME_OVERRIDES[symbol]]
    name = uni.get(symbol, {}).get("name", symbol)
    return [name.split()[0].lower()]


def _head(path: str, n: int = HEAD_CHARS) -> str:
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return fh.read(n).lower()


def _raw_files():
    return sorted(glob.glob(str(RAW_DIR / "*.txt")))


def _ticker_of(path: str) -> str:
    return os.path.basename(path).split("__")[0]


# ── 0. sanity ──────────────────────────────────────────────────────────────

def test_raw_corpus_nonempty():
    files = _raw_files()
    assert len(files) > 300, f"unexpectedly few raw files: {len(files)}"


# ── 1. собствено име присъства (глобален контаминационен чек) ───────────────

def test_own_company_name_present():
    uni = _load_universe()
    failures = []
    for f in _raw_files():
        t = _ticker_of(f)
        toks = _name_tokens(t, uni)
        h = _head(f)
        if not any(tok in h for tok in toks):
            failures.append((os.path.basename(f), toks))
    assert not failures, (
        f"{len(failures)} raw файла без собствено име в първите {HEAD_CHARS} знака "
        f"(възможна контаминация): {failures[:10]}"
    )


# ── 2. грешен (чужд) токен отсъства за 5-те бивши контаминирани ─────────────

def test_no_wrong_company_token():
    hits = []
    for f in _raw_files():
        t = _ticker_of(f)
        wrong = WRONG_TOKEN.get(t)
        if not wrong:
            continue
        if wrong in _head(f):
            hits.append((os.path.basename(f), wrong))
    assert not hits, f"грешен-компания токен намерен (контаминация): {hits}"


# ── 3. CIK-мач срещу авторитетния snapshot (хваща дрейф) ────────────────────

def test_universe_cik_matches_snapshot():
    assert CIK_SNAPSHOT.exists(), f"липсва snapshot: {CIK_SNAPSHOT}"
    raw = json.load(open(CIK_SNAPSHOT, encoding="utf-8"))
    snap = {}
    for e in raw.values():
        snap[str(e["ticker"]).upper()] = str(e["cik_str"])

    uni = _load_universe()
    problems = []
    for sym, info in uni.items():
        auth = snap.get(sym.upper())
        if auth is None:
            problems.append(f"{sym}: отсъства от company_tickers snapshot")
            continue
        ucik = info["cik"]
        if ucik and str(int(ucik)) != str(int(auth)):
            problems.append(f"{sym}: universe cik {ucik} != авторитетен {auth}")
    assert not problems, "CIK дрейф спрямо snapshot: " + "; ".join(problems)


# ── 4. покритие: всеки активен тикер има корпус (освен документираните) ─────

def test_enabled_tickers_have_corpus():
    uni = _load_universe()
    counts = {}
    for f in _raw_files():
        counts[_ticker_of(f)] = counts.get(_ticker_of(f), 0) + 1
    missing = [t for t in uni if t not in KNOWN_MISSING and counts.get(t, 0) == 0]
    assert not missing, (
        f"активни тикери без raw корпус и извън KNOWN_MISSING: {missing}"
    )
