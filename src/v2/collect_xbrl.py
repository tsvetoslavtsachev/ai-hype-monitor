"""
collect_xbrl.py — F-крак колектор (Фаза 1).
===========================================
Детерминистично фундаментално хранилище от SEC XBRL companyfacts.
LLM НИКОГА в числовия път — тук всичко е аритметика/парсване на официални XBRL факти.

За всеки тикер от universe.csv:
  1. дърпа https://data.sec.gov/api/xbrl/companyfacts/CIK{10}.json
  2. по fallback веригите (config: src/v2/concepts.py) вади ТРИМЕСЕЧНИ серии
     (duration факти с 80..100 дни) + shares (instant, последна per filing)
  3. записва app/data/v2/facts/{TICKER}.json — append-only, bitemporal:
     всеки запис {concept, xbrl_tag, period_start, period_end, value, unit,
     form, known_at=filed, accn}; всички винтиджи се пазят (ревизиите не трият).

Идемпотентност: изходът НЯМА timestamp; повторен пуск със същите upstream данни
дава байт-идентичен файл (union + детерминистично сортиране).
None ≠ 0: липсващ концепт просто не поражда записи (видимо в покритието), без прокси.

Windows/cp1252: печатаме само ASCII; файлове четем/пишем с encoding="utf-8".
"""

import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concepts import (  # noqa: E402
    CONCEPT_CHAINS, CONCEPT_KIND, QUARTER_MIN_DAYS, QUARTER_MAX_DAYS,
)

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "config" / "universe.csv"
FACTS_DIR = ROOT / "app" / "data" / "v2" / "facts"

HEADERS = {"User-Agent": "Tsachev Research tsvetoslav.tsachev@gmail.com",
           "Accept-Encoding": "gzip, deflate"}
RATE = 0.15
SOURCE = "SEC XBRL companyfacts (data.sec.gov)"

# ── мрежов слой ─────────────────────────────────────────────────────────────

def sec_get(url: str, timeout: int = 30):
    """GET с rate limit + retry/backoff (5/10/15s) при 429/500/502/503."""
    backoffs = (5, 10, 15)
    resp = None
    for attempt in range(len(backoffs) + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            time.sleep(RATE)
            if resp.status_code in (429, 500, 502, 503) and attempt < len(backoffs):
                w = backoffs[attempt]
                print(f"    [retry {attempt+1}] HTTP {resp.status_code} -> {w}s", flush=True)
                time.sleep(w)
                continue
            return resp
        except Exception as e:
            if attempt < len(backoffs):
                w = backoffs[attempt]
                print(f"    [retry {attempt+1}] {e} -> {w}s", flush=True)
                time.sleep(w)
                continue
            print(f"    [ERROR] giving up: {e}", flush=True)
            return None
    return resp


def _resolve_missing_ciks(symbols: set) -> dict:
    if not symbols:
        return {}
    r = sec_get("https://www.sec.gov/files/company_tickers.json")
    out = {}
    if r is not None and r.status_code == 200:
        try:
            for e in r.json().values():
                tk = str(e.get("ticker", "")).upper()
                if tk in symbols:
                    out[tk] = str(e["cik_str"])
        except Exception as exc:
            print(f"  [WARN] company_tickers parse: {exc}", flush=True)
    return out


def load_companies() -> dict:
    """{symbol: {name, cik}} от universe.csv (source of truth), празен CIK през fallback."""
    companies, missing = {}, set()
    with open(UNIVERSE, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("enabled", "1")).strip() not in ("1", "true", "True"):
                continue
            sym = row["symbol"].strip()
            cik = str(row.get("cik", "") or "").strip()
            companies[sym] = {"name": row["name"].strip(), "cik": cik}
            if not cik:
                missing.add(sym.upper())
    resolved = _resolve_missing_ciks(missing)
    for sym, info in companies.items():
        if not info["cik"]:
            info["cik"] = resolved.get(sym.upper(), "")
    return {s: i for s, i in companies.items() if i["cik"]}


# ── извличане на факти ──────────────────────────────────────────────────────

def _iter_tag_facts(facts_json: dict, xbrl_tag: str):
    """Дава (unit, fact_entry) за даден namespace:tag, ако присъства."""
    ns, _, tag = xbrl_tag.partition(":")
    node = facts_json.get("facts", {}).get(ns, {}).get(tag)
    if not node:
        return
    for unit, entries in node.get("units", {}).items():
        for e in entries:
            yield unit, e


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def extract_records(facts_json: dict) -> list:
    """Вади тримесечни (duration) + instant (shares) записи по веригите."""
    records = []
    for concept, chain in CONCEPT_CHAINS.items():
        kind = CONCEPT_KIND[concept]
        for xbrl_tag in chain:
            for unit, e in _iter_tag_facts(facts_json, xbrl_tag):
                end = e.get("end")
                filed = e.get("filed")
                if not end or not filed or "val" not in e:
                    continue
                if kind == "duration":
                    start = e.get("start")
                    if not start:
                        continue
                    d = _days(start, end)
                    if d < QUARTER_MIN_DAYS or d > QUARTER_MAX_DAYS:
                        continue  # само тримесечни; годишни/YTD се пропускат
                    period_start = start
                else:  # instant (shares)
                    period_start = end
                records.append({
                    "concept": concept,
                    "xbrl_tag": xbrl_tag,
                    "period_start": period_start,
                    "period_end": end,
                    "value": e["val"],
                    "unit": unit,
                    "form": e.get("form", ""),
                    "known_at": filed,
                    "accn": e.get("accn", ""),
                })
    return records


# ── детерминистична сериализация (idempotency) ──────────────────────────────

def _dedup_key(r: dict) -> tuple:
    return (r["concept"], r["xbrl_tag"], r["unit"], r["period_start"],
            r["period_end"], r["known_at"], r["accn"], r["value"])


def _sort_key(r: dict) -> tuple:
    return (r["concept"], r["period_end"], r["period_start"],
            r["known_at"], r["xbrl_tag"], r["accn"])


def merge_records(existing: list, new: list) -> list:
    """Append-only union + dedup (ревизиите/винтиджите се пазят)."""
    seen, out = set(), []
    for r in list(existing) + list(new):
        k = _dedup_key(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    out.sort(key=_sort_key)
    return out


def canonical_dump(ticker: str, cik: str, entity: str, records: list) -> str:
    """Байт-детерминистичен JSON (без timestamp) — гарантира 0-диф при повторен пуск."""
    recs = sorted(records, key=_sort_key)
    obj = {
        "ticker": ticker,
        "cik": str(cik),
        "entity_name": entity,
        "source": SOURCE,
        "schema": "bitemporal append-only; record={concept,xbrl_tag,period_start,"
                  "period_end,value,unit,form,known_at,accn}",
        "record_count": len(recs),
        "facts": recs,
    }
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_existing(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("facts", [])
    except Exception:
        return []


# ── главна ──────────────────────────────────────────────────────────────────

def main():
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    companies = load_companies()
    print("=== F-leg XBRL collector (Phase 1) ===", flush=True)
    print(f"companies: {len(companies)} (source: config/universe.csv)", flush=True)

    coverage = {}
    for sym, info in companies.items():
        cik = info["cik"]
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json"
        r = sec_get(url)
        if r is None or r.status_code != 200:
            print(f"[{sym}] companyfacts HTTP {getattr(r,'status_code','ERR')} -> 0 records", flush=True)
            path = FACTS_DIR / f"{sym}.json"
            merged = merge_records(load_existing(path), [])
            path.write_text(canonical_dump(sym, cik, info["name"], merged), encoding="utf-8")
            coverage[sym] = {}
            continue
        fj = r.json()
        entity = fj.get("entityName", info["name"])
        new = extract_records(fj)
        path = FACTS_DIR / f"{sym}.json"
        merged = merge_records(load_existing(path), new)
        path.write_text(canonical_dump(sym, cik, entity, merged), encoding="utf-8")
        # покритие: концепт -> брой различни тримесечия
        cov = {}
        for c in CONCEPT_CHAINS:
            periods = {rr["period_end"] for rr in merged if rr["concept"] == c}
            cov[c] = len(periods)
        coverage[sym] = cov
        print(f"[{sym}] {entity}: {len(merged)} records | "
              + " ".join(f"{c}={cov[c]}" for c in CONCEPT_CHAINS), flush=True)

    # компактна покритие таблица (None-тата видими като 0 тримесечия)
    print("\n=== coverage (quarters per concept) ===", flush=True)
    cols = list(CONCEPT_CHAINS.keys())
    print("ticker  " + " ".join(f"{c[:9]:>9}" for c in cols), flush=True)
    for sym in sorted(coverage):
        cov = coverage[sym]
        print(f"{sym:7} " + " ".join(f"{cov.get(c,0):>9}" for c in cols), flush=True)
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
