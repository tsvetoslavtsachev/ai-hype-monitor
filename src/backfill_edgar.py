"""
backfill_edgar.py
=================
Исторически backfill на SEC EDGAR 8-K filings от Q4 2022 до днес.
Анализира AI rhetoric в earnings press releases (EX-99.1 / EX-99.2).

Методология:
  1. Намираме всички 8-K filings за всяка компания от Q4 2022
  2. За всяко filing листваме файловете в директорията
  3. Намираме EX-99.1 / EX-99.2 (press release / CFO commentary)
  4. Анализираме AI keyword density vs. financial substance

Изход: app/data/rhetoric_history.json
"""

import json
import re
import time
import argparse
from datetime import datetime, date
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ── EDGAR API настройки ───────────────────────────────────────────────────

EDGAR_BASE   = "https://data.sec.gov"
EDGAR_ARCH   = "https://www.sec.gov/Archives/edgar/data"
HEADERS = {
    "User-Agent": "AI-Hype-Monitor research@elana.net",
    "Accept-Encoding": "gzip, deflate",
}
RATE_LIMIT_SLEEP = 0.12   # ~8 req/sec (лимит е 10)

# ── Речник на ключовите думи ──────────────────────────────────────────────

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "generative ai", "gen ai",
    "neural network", "natural language processing",
    "foundation model", "transformer model",
    "inference", "training workload", "ai infrastructure",
    "ai platform", "ai solution", "ai capability", "ai-powered",
    "ai-driven", "ai-enabled", "copilot", "ai agent", "agentic",
    "ai opportunity", "ai investment", "ai demand", "ai accelerat",
    "ai workload", "data center ai", "ai chip", "ai compute",
    "ai model", "ai product", "ai feature", "ai revenue",
    "accelerated computing", "gpu cluster", "hopper", "blackwell",
    "h100", "h200", "gb200", "ai factory",
]

# Кратките " ai " се броят отделно с regex
AI_SHORT_PATTERN = re.compile(r'\bai\b', re.IGNORECASE)

SUBSTANCE_KEYWORDS = [
    "revenue", "earnings", "profit", "margin", "ebitda", "eps",
    "guidance", "outlook", "forecast",
    "operating income", "net income", "cash flow",
    "return on", "basis point",
    "year-over-year", "sequential", "backlog", "bookings", "orders",
    "market share", "unit", "shipment", "capacity",
    "capex", "capital expenditure", "free cash flow", "buyback",
    "dividend", "debt", "balance sheet", "diluted",
]

# ── Компании с CIK ────────────────────────────────────────────────────────

COMPANIES = {
    "NVDA":  {"name": "Nvidia",              "cik": "1045810"},
    "AMD":   {"name": "AMD",                 "cik": "2488"},
    "AVGO":  {"name": "Broadcom",            "cik": "1730168"},
    "MRVL":  {"name": "Marvell Technology",  "cik": "1058057"},
    "QCOM":  {"name": "Qualcomm",            "cik": "804328"},
    "ASML":  {"name": "ASML Holding",        "cik": "937966"},
    "AMAT":  {"name": "Applied Materials",   "cik": "796343"},
    "LRCX":  {"name": "Lam Research",        "cik": "707549"},
    "KLAC":  {"name": "KLA Corp",            "cik": "319201"},
    "SNPS":  {"name": "Synopsys",            "cik": "883241"},
    "CDNS":  {"name": "Cadence Design",      "cik": "813672"},
    "MU":    {"name": "Micron Technology",   "cik": "723125"},
    "WDC":   {"name": "Western Digital",     "cik": "106040"},
    "ANET":  {"name": "Arista Networks",     "cik": "1313925"},
    "CIEN":  {"name": "Ciena",               "cik": "936395"},
    "COHR":  {"name": "Coherent",            "cik": "820318"},
    "VRT":   {"name": "Vertiv Holdings",     "cik": "1779128"},
    "ETN":   {"name": "Eaton Corp",          "cik": "1551182"},
    "DELL":  {"name": "Dell Technologies",   "cik": "1571996"},
    "SMCI":  {"name": "Super Micro Computer","cik": "893691"},
    "MSFT":  {"name": "Microsoft",           "cik": "789019"},
    "GOOGL": {"name": "Alphabet",            "cik": "1652044"},
    "AMZN":  {"name": "Amazon",              "cik": "1018724"},
    "META":  {"name": "Meta Platforms",      "cik": "1326801"},
    "ORCL":  {"name": "Oracle",              "cik": "1341439"},
    "PLTR":  {"name": "Palantir",            "cik": "1321655"},
    "CRM":   {"name": "Salesforce",          "cik": "1108524"},
    "NOW":   {"name": "ServiceNow",          "cik": "1373715"},
    "SNOW":  {"name": "Snowflake",           "cik": "1640147"},
}

# ── HTML → текст ──────────────────────────────────────────────────────────

def html_to_text(html: str) -> str:
    """Премахва HTML тагове и нормализира whitespace."""
    # Премахни script/style блокове
    text = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', ' ', html,
                  flags=re.DOTALL | re.IGNORECASE)
    # Премахни всички тагове
    text = re.sub(r'<[^>]+>', ' ', text)
    # HTML entities
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    # Нормализирай whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── NLP анализ ────────────────────────────────────────────────────────────

def analyze_text(text: str) -> dict:
    """Анализира текст и връща rhetoric метрики."""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = max(len(words), 1)

    # AI mentions: дълги фрази + кратко "ai"
    ai_count = 0
    for kw in AI_KEYWORDS:
        ai_count += text_lower.count(kw)
    # Кратко "ai" само ако не е вече преброено в дълга фраза
    short_ai = len(AI_SHORT_PATTERN.findall(text))
    # Добавяме само "самостоятелни" ai (приблизително)
    ai_count += max(0, short_ai - ai_count)

    # Financial substance
    substance_count = 0
    for kw in SUBSTANCE_KEYWORDS:
        substance_count += text_lower.count(kw)

    # Метрики
    ai_density = round(ai_count / total_words * 100, 3)

    total_mentions = ai_count + substance_count
    if total_mentions > 0:
        substance_ratio = round(substance_count / total_mentions, 3)
    else:
        substance_ratio = 0.5

    # Rhetoric Score: 0 = чисто финансово, 100 = чист hype
    ai_score       = min(ai_density * 8, 100)
    hype_ratio     = 1.0 - substance_ratio
    rhetoric_score = round(ai_score * 0.6 + hype_ratio * 100 * 0.4, 1)
    rhetoric_score = max(0.0, min(100.0, rhetoric_score))

    return {
        "word_count":          total_words,
        "ai_mentions":         ai_count,
        "substance_mentions":  substance_count,
        "ai_density":          ai_density,
        "substance_ratio":     substance_ratio,
        "rhetoric_score":      rhetoric_score,
    }


# ── EDGAR: списък с filings ───────────────────────────────────────────────

def get_filings_list(cik: str, start_date: str, end_date: str) -> list[dict]:
    """Връща 8-K filings за компанията в дадения период."""
    url = f"{EDGAR_BASE}/submissions/CIK{cik.zfill(10)}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        time.sleep(RATE_LIMIT_SLEEP)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        print(f"    [ERROR] submissions: {e}")
        return []

    recent      = data.get("filings", {}).get("recent", {})
    forms       = recent.get("form", [])
    dates       = recent.get("filingDate", [])
    accessions  = recent.get("accessionNumber", [])

    filings = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        fd = dates[i] if i < len(dates) else ""
        if not (start_date <= fd <= end_date):
            continue
        acc = accessions[i] if i < len(accessions) else ""
        filings.append({"filing_date": fd, "accession": acc, "cik": cik})

    filings.sort(key=lambda x: x["filing_date"])
    return filings


# ── EDGAR: намери exhibit файл ────────────────────────────────────────────

def find_exhibit_url(cik: str, accession: str) -> str | None:
    """
    Листва файловете в EDGAR директорията на filing-а и
    връща URL на EX-99.1 / EX-99.2 (press release / CFO commentary).
    """
    acc_clean = accession.replace("-", "")
    cik_int   = int(cik)
    dir_url   = f"{EDGAR_ARCH}/{cik_int}/{acc_clean}/"

    try:
        resp = requests.get(dir_url, headers=HEADERS, timeout=20)
        time.sleep(RATE_LIMIT_SLEEP)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    # Намери всички .htm файлове (без index)
    htm_files = re.findall(r'href="(/Archives/edgar/data/[^"]+\.htm)"',
                           resp.text, re.IGNORECASE)

    # Приоритет: файлове с "ex99", "press", "earnings", "result", "cfo", "commentary"
    priority_patterns = [
        r'ex.?99', r'press', r'earnings', r'result', r'cfo',
        r'commentary', r'release', r'q[1-4]fy', r'q[1-4]20',
    ]

    candidates = []
    for f in htm_files:
        fname = f.split("/")[-1].lower()
        if "index" in fname or fname.startswith("r") and fname[1:].isdigit():
            continue
        score = sum(1 for p in priority_patterns if re.search(p, fname))
        if score > 0:
            candidates.append((score, f"https://www.sec.gov{f}"))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    # Fallback: вземи първия .htm файл, който не е cover page
    for f in htm_files:
        fname = f.split("/")[-1].lower()
        if "index" not in fname and not (fname.startswith("r") and len(fname) < 8):
            return f"https://www.sec.gov{f}"

    return None


# ── EDGAR: вземи текст на exhibit ─────────────────────────────────────────

def fetch_exhibit_text(url: str) -> str:
    """Тегли и почиства текста на exhibit документ."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        time.sleep(RATE_LIMIT_SLEEP)
        if resp.status_code != 200:
            return ""
        return html_to_text(resp.text)
    except Exception as e:
        return ""


# ── Квартална агрегация ───────────────────────────────────────────────────

def date_to_quarter(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d")
    q  = (dt.month - 1) // 3 + 1
    return f"Q{q} {dt.year}"


def aggregate_to_quarters(analyzed: list[dict]) -> list[dict]:
    quarters: dict[str, list] = {}
    for f in analyzed:
        q = date_to_quarter(f["filing_date"])
        quarters.setdefault(q, []).append(f)

    result = []
    for q in sorted(quarters.keys()):
        items = quarters[q]
        result.append({
            "quarter":         q,
            "rhetoric_score":  round(sum(x["rhetoric_score"] for x in items) / len(items), 1),
            "ai_density":      round(sum(x["ai_density"]     for x in items) / len(items), 3),
            "substance_ratio": round(sum(x["substance_ratio"] for x in items) / len(items), 3),
            "filing_count":    len(items),
            "filing_date":     items[-1]["filing_date"],
        })
    return result


def _compute_trend(quarters: list[dict]) -> str:
    if len(quarters) < 2:
        return "stable"
    delta = quarters[-1]["rhetoric_score"] - quarters[-2]["rhetoric_score"]
    if delta > 3:   return "rising"
    if delta < -3:  return "falling"
    return "stable"


# ── Главна функция ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",  default="app/data/rhetoric_history.json")
    parser.add_argument("--start",   default="2022-10-01")
    parser.add_argument("--end",     default=date.today().isoformat())
    parser.add_argument("--max-per-company", type=int, default=20)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== AI Hype Monitor — SEC EDGAR Backfill (v2) ===")
    print(f"Период: {args.start} → {args.end}")
    print(f"Компании: {len(COMPANIES)}")
    print()

    result = {
        "generated_at": datetime.now().isoformat() + "Z",
        "start_date":   args.start,
        "end_date":     args.end,
        "source":       "SEC EDGAR 8-K Exhibits (EX-99.1/EX-99.2)",
        "methodology":  "Lexicon-based AI keyword density + financial substance ratio",
        "companies":    {},
        "sector_trend": [],
    }

    all_quarters: dict[str, list] = {}

    for symbol, meta in COMPANIES.items():
        print(f"  {symbol} ({meta['name']})...")
        cik = meta["cik"]

        filings = get_filings_list(cik, args.start, args.end)
        if not filings:
            print(f"    → 0 filings")
            continue

        # Вземи равномерно разпределени filings
        if len(filings) > args.max_per_company:
            step = max(1, len(filings) // args.max_per_company)
            filings = filings[::step][:args.max_per_company]

        print(f"    → {len(filings)} filings за анализ")

        analyzed = []
        for fi in filings:
            exhibit_url = find_exhibit_url(cik, fi["accession"])
            if not exhibit_url:
                continue

            text = fetch_exhibit_text(exhibit_url)
            if len(text) < 300:
                continue

            metrics = analyze_text(text)
            analyzed.append({
                "filing_date":   fi["filing_date"],
                "accession":     fi["accession"],
                "exhibit_url":   exhibit_url,
                **metrics,
            })

        if not analyzed:
            print(f"    → Не успяхме да анализираме текстове")
            continue

        quarters = aggregate_to_quarters(analyzed)
        latest   = quarters[-1] if quarters else {}

        result["companies"][symbol] = {
            "symbol":                symbol,
            "name":                  meta["name"],
            "cik":                   cik,
            "latest_rhetoric_score": latest.get("rhetoric_score", 0),
            "rhetoric_trend":        _compute_trend(quarters),
            "quarters":              quarters,
            "filings_analyzed":      len(analyzed),
        }

        for q in quarters:
            all_quarters.setdefault(q["quarter"], []).append(q["rhetoric_score"])

        print(f"    → Rhetoric score: {latest.get('rhetoric_score', '?')} | "
              f"Trend: {_compute_trend(quarters)} | "
              f"Filings OK: {len(analyzed)}")

    # Sector trend
    sector_trend = []
    for q in sorted(all_quarters.keys()):
        scores = all_quarters[q]
        sector_trend.append({
            "quarter":                   q,
            "sector_avg_rhetoric_score": round(sum(scores) / len(scores), 1),
            "companies_count":           len(scores),
        })

    result["sector_trend"] = sector_trend
    result["meta"] = {
        "companies_analyzed": len(result["companies"]),
        "quarters_covered":   len(sector_trend),
        "first_quarter":      sector_trend[0]["quarter"]  if sector_trend else None,
        "last_quarter":       sector_trend[-1]["quarter"] if sector_trend else None,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print()
    print(f"=== Резултат ===")
    print(f"Компании:   {len(result['companies'])}/{len(COMPANIES)}")
    print(f"Тримесечия: {len(sector_trend)}")
    if sector_trend:
        print(f"Период:     {sector_trend[0]['quarter']} → {sector_trend[-1]['quarter']}")
    print(f"Файл:       {output_path}")


if __name__ == "__main__":
    main()
