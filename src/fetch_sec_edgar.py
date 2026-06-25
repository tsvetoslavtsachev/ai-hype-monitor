"""
fetch_sec_edgar.py — AI Hype Monitor · SEC EDGAR Модул
=======================================================
Дърпа 8-K (Earnings Press Releases) и 10-Q (Quarterly Reports) от SEC EDGAR
за компаниите от AI Value Chain.

Безплатен, без API ключ. Изисква само User-Agent header.

Изходен файл: app/data/sec_filings.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import requests

# ── Пътища ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG_DIR = ROOT / "config"
APP_DATA_DIR = ROOT / "app" / "data"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = APP_DATA_DIR / "sec_filings.json"

# ── SEC EDGAR Config ─────────────────────────────────────────────────────────
SEC_BASE = "https://data.sec.gov"
SEC_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FULL = "https://www.sec.gov/Archives/edgar"

# ВАЖНО: SEC изисква User-Agent с контакт
USER_AGENT = "AI-Hype-Monitor tsvetoslav@elana.net"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}

# Брой последни filings на компания
MAX_FILINGS_PER_COMPANY = 8   # ~2 години тримесечни отчети
REQUEST_SLEEP = 0.3            # SEC rate limit: 10 req/sec


# ── SEC EDGAR API ─────────────────────────────────────────────────────────────

def _get_company_filings(cik: str, form_type: str = "8-K",
                          max_results: int = MAX_FILINGS_PER_COMPANY) -> list[dict]:
    """Взема последните filings за компания по CIK."""
    cik_padded = str(cik).zfill(10)
    url = f"{SEC_BASE}/submissions/CIK{cik_padded}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"WARN SEC EDGAR CIK {cik}: {e}", file=sys.stderr)
        return []

    filings = data.get("filings", {}).get("recent", {})
    if not filings:
        return []

    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])

    results = []
    for i, form in enumerate(forms):
        if form != form_type:
            continue
        if len(results) >= max_results:
            break
        acc = accessions[i].replace("-", "")
        results.append({
            "form": form,
            "date": dates[i],
            "accession": accessions[i],
            "accession_clean": acc,
            "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
            "cik": cik,
        })

    return results


def _get_filing_text(cik: str, accession_clean: str, primary_doc: str) -> Optional[str]:
    """Дърпа текста на конкретен filing от EDGAR Archives."""
    cik_padded = str(cik).zfill(10)
    # Опитваме primary document
    url = f"{EDGAR_FULL}/{cik_padded}/{accession_clean}/{primary_doc}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        text = resp.text
        # Премахваме HTML тагове ако е HTML документ
        if "<html" in text.lower() or "<!doctype" in text.lower():
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&nbsp;", " ", text)
            text = re.sub(r"&amp;", "&", text)
            text = re.sub(r"&lt;", "<", text)
            text = re.sub(r"&gt;", ">", text)
        # Нормализираме whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:50000]  # Ограничаваме до 50K символа
    except Exception as e:
        print(f"WARN filing text {accession_clean}: {e}", file=sys.stderr)
        return None


def _get_filing_index(cik: str, accession_clean: str) -> list[dict]:
    """Взема индекса на filing за намиране на правилния документ."""
    cik_padded = str(cik).zfill(10)
    url = f"{EDGAR_FULL}/{cik_padded}/{accession_clean}/{accession_clean}-index.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("directory", {}).get("item", [])
    except Exception:
        return []


# ── Намиране на CIK по тикър ──────────────────────────────────────────────────

def _lookup_cik(symbol: str) -> Optional[str]:
    """Търси CIK по тикър символ чрез EDGAR company search."""
    url = f"{SEC_BASE}/submissions/CIK{symbol}.json"
    # Опитваме директно с тикър (не работи за всички)
    # По-надежден: company_tickers.json
    try:
        tickers_url = f"{SEC_BASE}/files/company_tickers.json"
        resp = requests.get(tickers_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        tickers = resp.json()
        for entry in tickers.values():
            if entry.get("ticker", "").upper() == symbol.upper():
                return str(entry["cik_str"])
    except Exception as e:
        print(f"WARN CIK lookup {symbol}: {e}", file=sys.stderr)
    return None


# ── Главна функция ────────────────────────────────────────────────────────────

def run(fetch_text: bool = True, log=print) -> dict:
    """Дърпа 8-K filings за всички компании с известен CIK."""
    import pandas as pd

    universe_df = pd.read_csv(CONFIG_DIR / "universe.csv")
    universe_df = universe_df[universe_df["enabled"] == 1].copy()

    # Зареждаме CIK lookup таблица от EDGAR веднъж
    log("[fetch_sec] Loading EDGAR company tickers...")
    cik_lookup = {}
    try:
        resp = requests.get(
            f"{SEC_BASE}/files/company_tickers.json",
            headers=HEADERS, timeout=20
        )
        resp.raise_for_status()
        tickers_data = resp.json()
        for entry in tickers_data.values():
            cik_lookup[entry["ticker"].upper()] = str(entry["cik_str"])
        log(f"[fetch_sec] Loaded {len(cik_lookup)} tickers from EDGAR")
    except Exception as e:
        log(f"WARN: Could not load EDGAR tickers: {e}")

    all_filings = {}
    cutoff_date = (date.today() - timedelta(days=365 * 4)).isoformat()  # 4 години назад

    for _, row in universe_df.iterrows():
        sym = row["symbol"]

        # Намираме CIK
        cik = None
        if pd.notna(row.get("cik")) and str(row.get("cik", "")).strip():
            cik = str(int(float(row["cik"])))
        else:
            cik = cik_lookup.get(sym.upper())

        if not cik:
            log(f"  {sym:6s} — CIK не е намерен, пропускаме")
            continue

        log(f"  {sym:6s} CIK={cik} — дърпаме 8-K filings...")
        filings = _get_company_filings(cik, form_type="8-K")
        time.sleep(REQUEST_SLEEP)

        # Филтрираме само тримесечни earnings (след cutoff)
        recent_filings = [f for f in filings if f["date"] >= cutoff_date]

        company_filings = []
        for filing in recent_filings:
            entry = {
                "symbol": sym,
                "form": filing["form"],
                "date": filing["date"],
                "accession": filing["accession"],
                "cik": cik,
                "text_length": 0,
                "text_fetched": False,
            }

            if fetch_text and filing.get("primary_doc"):
                text = _get_filing_text(cik, filing["accession_clean"], filing["primary_doc"])
                time.sleep(REQUEST_SLEEP)
                if text:
                    entry["text"] = text[:10000]  # Запазваме само първите 10K за storage
                    entry["text_length"] = len(text)
                    entry["text_fetched"] = True

            company_filings.append(entry)

        all_filings[sym] = {
            "symbol": sym,
            "name": row["name"],
            "layer": row["layer"],
            "cik": cik,
            "filings_count": len(company_filings),
            "filings": company_filings,
        }
        log(f"    → {len(company_filings)} filings намерени")

    output = {
        "updated_at": date.today().isoformat(),
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "companies": all_filings,
        "meta": {
            "total_companies": len(all_filings),
            "total_filings": sum(c["filings_count"] for c in all_filings.values()),
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"[fetch_sec] Written → {OUTPUT_FILE}")

    return output


if __name__ == "__main__":
    run()
