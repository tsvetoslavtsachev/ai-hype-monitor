"""
build_corpus.py
===============
Изгражда пълния текстови корпус от SEC EDGAR 8-K filings (Q4 2022 → сега).
Запазва:
  - data/corpus/raw/{SYMBOL}__{QUARTER}__{DATE}.txt  — оригинален текст
  - data/corpus/{SYMBOL}.json                        — метаданни + NLP резултати
  - data/corpus_stats.json                           — базова линия за нормализация

Стратегия:
  1. Тегли само 8-K с items 2.02 (Results of Operations) или 9.01 (Financial Statements)
  2. Взима EX-99.1 (press release) или EX-99.2 (CFO commentary) exhibit
  3. Запазва оригиналния текст като .txt файл (frozen база)
  4. Изчислява NLP метрики: ai_density, substance_ratio, finance_density
  5. Нормализира по корпусна базова линия (Z-score → 0-100)
"""

import csv
import json
import re
import time
import statistics
import requests
from pathlib import Path
from datetime import datetime

# ── Конфигурация ──────────────────────────────────────────────────────────

HEADERS  = {"User-Agent": "Tsachev Research tsvetoslav.tsachev@gmail.com",
            "Accept-Encoding": "gzip, deflate"}
BASE_SEC  = "https://www.sec.gov"
BASE_DATA = "https://data.sec.gov"
RATE      = 0.15   # секунди между заявки

DATA_DIR   = Path("app/data")
CORPUS_DIR = DATA_DIR / "corpus"
RAW_DIR    = CORPUS_DIR / "raw"
CORPUS_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2022-10-01"

# ── AI ключови думи ───────────────────────────────────────────────────────

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "llm", "generative ai",
    "gen ai", "genai", "foundation model", "transformer model",
    "chatgpt", "copilot", "gemini", "claude", "gpt-4", "gpt4",
    "openai", "anthropic",
    "gpu cluster", "ai accelerator", "ai chip", "ai inference",
    "ai training", "ai workload", "ai infrastructure", "ai compute",
    "ai-powered", "ai-driven", "ai-enabled", "ai-assisted",
    "ai agent", "agentic ai", "autonomous ai",
    "nvidia h100", "nvidia h200", "nvidia blackwell",
    "ai cloud", "ai platform", "ai solution", "ai revenue",
    "ai demand", "ai opportunity", "ai adoption",
]

FINANCE_KEYWORDS = [
    "revenue", "billion", "million", "growth", "margin", "profit",
    "earnings", "guidance", "forecast", "quarter", "fiscal",
    "year-over-year", "yoy", "sequential", "backlog", "bookings",
    "operating income", "gross margin", "free cash flow", "eps",
    "diluted", "non-gaap", "adjusted",
]

NUMBER_PATTERN = re.compile(
    r'(\$[\d,.]+\s*(?:billion|million|B|M)\b|'
    r'\d+[\d,.]*\s*%|'
    r'\d+x\s*(?:growth|increase|more)\b|'
    r'up\s+\d+%|grew\s+\d+%|'
    r'increased\s+\d+%)',
    re.IGNORECASE
)

# ── Компании ──────────────────────────────────────────────────────────────
# ЕДИНСТВЕН източник на истина: config/universe.csv (колона `cik`).
# ИСТОРИЧЕСКИ БЪГ (поправен): преди тук имаше hardcoded речник с CIK-ове, който
# се беше разминал с реалните CIK-ове и замърси корпуса — напр. AMAT сочеше към
# CIK-а на Adobe, DELL към този на SAIC, SMCI към Stryker, PWR към Salem Media,
# LITE към Axalta. Затова тегленето по тикер
# връщаше earnings press releases на ЧУЖДИ компании. Сега CIK-овете идват само
# от universe.csv; при празен CIK — резолвим детерминистично през EDGAR
# company_tickers.json (точен ticker match).

CONFIG_UNIVERSE = Path(__file__).resolve().parent.parent / "config" / "universe.csv"


def _resolve_missing_ciks(symbols: set) -> dict:
    """Fallback CIK резолюция през SEC company_tickers.json (точен ticker match)."""
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
            print(f"  [WARN] company_tickers.json parse: {exc}", flush=True)
    return out


def load_companies() -> dict:
    """Зарежда {symbol: {name, cik}} от universe.csv (source of truth).

    Празен `cik` се резолвира през EDGAR company_tickers.json. Символи без
    намерен CIK се пропускат (с WARN).
    """
    companies: dict = {}
    missing: set = set()
    with open(CONFIG_UNIVERSE, encoding="utf-8-sig") as fh:
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
    dropped = [s for s, i in companies.items() if not i["cik"]]
    if dropped:
        print(f"  [WARN] CIK не е резолвиран, пропускаме: {dropped}", flush=True)
    return {s: i for s, i in companies.items() if i["cik"]}

# ── EDGAR функции ─────────────────────────────────────────────────────────

def sec_get(url: str, timeout: int = 20) -> requests.Response | None:
    """GET с rate limiting и retry."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            time.sleep(RATE)
            return r
        except Exception as e:
            print(f"    Retry {attempt+1}: {e}")
            time.sleep(2)
    return None


def get_earnings_8k_filings(cik: str) -> list[dict]:
    """
    Взима 8-K filings с items 2.02 (Results of Operations).
    Това са earnings announcements, не HR/governance 8-K.
    """
    cik_padded = cik.zfill(10)
    url = f"{BASE_DATA}/submissions/CIK{cik_padded}.json"
    r = sec_get(url)
    if not r or r.status_code != 200:
        return []

    data = r.json()
    recent = data.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    dates   = recent.get("filingDate", [])
    accnums = recent.get("accessionNumber", [])
    items   = recent.get("items", [""] * len(forms))

    result = []
    for form, dt, acc, item in zip(forms, dates, accnums, items):
        if form != "8-K":
            continue
        if dt < START_DATE:
            continue
        # Само earnings 8-K: item 2.02 = Results of Operations
        if "2.02" in str(item):
            result.append({"date": dt, "accession": acc, "items": item})

    # Ако няма 2.02, вземи всички 8-K (за компании като ASML, MRVL)
    if not result:
        for form, dt, acc, item in zip(forms, dates, accnums, items):
            if form == "8-K" and dt >= START_DATE:
                result.append({"date": dt, "accession": acc, "items": item})

    return result


def get_exhibit_text(cik: str, accession: str) -> tuple[str | None, str | None]:
    """
    Взима текста на EX-99.1 или EX-99.2 от 8-K filing.
    Връща (clean_text, exhibit_url).
    """
    cik_num = cik.lstrip("0")
    acc_clean = accession.replace("-", "")

    # Вземи filing index от www.sec.gov
    idx_url = f"{BASE_SEC}/Archives/edgar/data/{cik_num}/{acc_clean}/{accession}-index.htm"
    r = sec_get(idx_url)
    if not r or r.status_code != 200:
        return None, None

    # Намери EX-99.1 или EX-99.2 в таблицата
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
    exhibit_url = None
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        cells_text = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        cells_html = cells  # keep HTML for href extraction

        # Check if this row is EX-99.1 or EX-99.2
        row_text = ' '.join(cells_text)
        if re.search(r'EX-99\.[12]', row_text, re.IGNORECASE):
            # Extract href from this row
            href = re.search(r'href="(/Archives/edgar/data/[^"]+\.htm[^"]*)"',
                             row, re.IGNORECASE)
            if href:
                exhibit_url = BASE_SEC + href.group(1)
                break

    # FALLBACK (по-хлабав matcher): някои емитенти етикетират прессъобщението
    # EX-99 (без .1) или EX-99.01/.02 (водеща нула) — напр. ETN (EX-99),
    # CDNS (EX-99.01/.02). Стриктният `EX-99\.[12]` ги пропуска. Пуска се САМО
    # когато стриктният се провали, за да НЕ променя избора за работещите тикери.
    if not exhibit_url:
        for row in rows:
            cells_text = [re.sub(r'<[^>]+>', '', c).strip()
                          for c in re.findall(r'<td[^>]*>(.*?)</td>', row,
                                              re.DOTALL | re.IGNORECASE)]
            row_text = ' '.join(cells_text)
            if re.search(r'EX-99(\.\d{1,2})?\b', row_text, re.IGNORECASE):
                href = re.search(r'href="(/Archives/edgar/data/[^"]+\.htm[^"]*)"',
                                 row, re.IGNORECASE)
                if href:
                    exhibit_url = BASE_SEC + href.group(1)
                    break

    if not exhibit_url:
        return None, None

    # Fetch exhibit text
    r2 = sec_get(exhibit_url, timeout=25)
    if not r2 or r2.status_code != 200:
        return None, None

    # Clean HTML
    raw = r2.text
    # Remove scripts and styles
    raw = re.sub(r'<script[^>]*>.*?</script>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r'<style[^>]*>.*?</style>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', raw)
    # Fix entities
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'&amp;', '&', clean)
    clean = re.sub(r'&lt;', '<', clean)
    clean = re.sub(r'&gt;', '>', clean)
    clean = re.sub(r'&#\d+;', ' ', clean)
    clean = re.sub(r'&[a-z]+;', ' ', clean)
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()

    return (clean if len(clean) > 300 else None), exhibit_url


# ── NLP анализ ────────────────────────────────────────────────────────────

def analyze_text(text: str) -> dict:
    """
    Анализира текст и връща NLP метрики.
    """
    if not text or len(text) < 200:
        return {"ai_mentions": 0, "total_words": 0, "ai_density": 0.0,
                "substance_ratio": 0.0, "finance_density": 0.0}

    text_lower = text.lower()
    words = text_lower.split()
    total_words = len(words)
    if total_words < 100:
        return {"ai_mentions": 0, "total_words": total_words, "ai_density": 0.0,
                "substance_ratio": 0.0, "finance_density": 0.0}

    # AI mentions с позиции
    ai_positions = []
    for kw in AI_KEYWORDS:
        start = 0
        while True:
            pos = text_lower.find(kw, start)
            if pos == -1:
                break
            ai_positions.append(pos)
            start = pos + len(kw)

    ai_mentions = len(ai_positions)
    ai_density  = round(ai_mentions / total_words * 1000, 4)

    # Substance ratio — AI mentions последвани от числа
    substance_count = 0
    for pos in ai_positions:
        context = text[max(0, pos - 30): min(len(text), pos + 250)]
        if NUMBER_PATTERN.search(context):
            substance_count += 1
    substance_ratio = round(substance_count / ai_mentions, 3) if ai_mentions > 0 else 0.0

    # Finance density
    finance_mentions = sum(text_lower.count(kw) for kw in FINANCE_KEYWORDS)
    finance_density  = round(finance_mentions / total_words * 1000, 4)

    return {
        "ai_mentions":     ai_mentions,
        "total_words":     total_words,
        "ai_density":      ai_density,
        "substance_ratio": substance_ratio,
        "finance_density": finance_density,
    }


def date_to_quarter(dt: str) -> str:
    d = datetime.strptime(dt[:10], "%Y-%m-%d")
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


def safe_filename(s: str) -> str:
    return re.sub(r'[^\w\-_]', '_', s)


# ── Главна функция ────────────────────────────────────────────────────────

def main():
    COMPANIES = load_companies()
    print("=== AI Hype Monitor — Corpus Builder v2 ===", flush=True)
    print(f"Компании: {len(COMPANIES)} (source: config/universe.csv)", flush=True)
    print(f"Период: {START_DATE} → днес", flush=True)
    print(f"Raw текстове: {RAW_DIR}", flush=True)
    print()

    all_docs = []

    for symbol, info in COMPANIES.items():
        cik  = info["cik"]
        name = info["name"]
        corpus_file = CORPUS_DIR / f"{symbol}.json"

        # Зареди от кеш ако съществува
        if corpus_file.exists():
            with open(corpus_file) as f:
                existing = json.load(f)
            cached_docs = existing.get("filings", [])
            print(f"[{symbol}] {name} → кеш ({len(cached_docs)} docs)", flush=True)
            all_docs.extend(cached_docs)
            continue

        print(f"[{symbol}] {name} (CIK: {cik})", flush=True)

        # Вземи earnings 8-K filings
        filings = get_earnings_8k_filings(cik)
        print(f"  → {len(filings)} earnings 8-K filings", flush=True)

        company_docs = []
        for i, filing in enumerate(filings):
            dt  = filing["date"]
            acc = filing["accession"]
            quarter = date_to_quarter(dt)

            # Провери дали raw текст вече съществува
            raw_filename = f"{symbol}__{safe_filename(quarter)}__{dt}.txt"
            raw_path = RAW_DIR / raw_filename

            if raw_path.exists():
                text = raw_path.read_text(encoding="utf-8")
                exhibit_url = "cached"
            else:
                text, exhibit_url = get_exhibit_text(cik, acc)
                if text:
                    # Запази оригиналния текст
                    raw_path.write_text(text, encoding="utf-8")

            if not text or len(text) < 200:
                continue

            analysis = analyze_text(text)
            if analysis["total_words"] < 100:
                continue

            doc = {
                "symbol":          symbol,
                "name":            name,
                "quarter":         quarter,
                "filing_date":     dt,
                "accession":       acc,
                "exhibit_url":     exhibit_url or "",
                "raw_file":        raw_filename,
                "total_words":     analysis["total_words"],
                "ai_mentions":     analysis["ai_mentions"],
                "ai_density":      analysis["ai_density"],
                "substance_ratio": analysis["substance_ratio"],
                "finance_density": analysis["finance_density"],
            }
            company_docs.append(doc)
            all_docs.append(doc)

            print(f"  {dt} {quarter}: {analysis['ai_mentions']} AI mentions, "
                  f"density={analysis['ai_density']:.3f}, "
                  f"substance={analysis['substance_ratio']:.2f}", flush=True)

        # Запази corpus файл
        with open(corpus_file, "w", encoding="utf-8") as f:
            json.dump({"symbol": symbol, "name": name, "filings": company_docs},
                      f, ensure_ascii=False, indent=2)
        print(f"  → {len(company_docs)} документа запазени", flush=True)

    # ── Корпусна статистика ───────────────────────────────────────────────
    print()
    print("=== Корпусна статистика ===", flush=True)

    densities = [d["ai_density"] for d in all_docs if d["ai_density"] > 0]
    all_densities = [d["ai_density"] for d in all_docs]  # включва нулите

    if not densities:
        print("ГРЕШКА: Няма документи с AI mentions!")
        return

    corpus_mean   = statistics.mean(densities)
    corpus_stdev  = statistics.stdev(densities) if len(densities) > 1 else 1.0
    corpus_median = statistics.median(densities)
    # За нормализация включваме и нулите (много компании имат 0 AI mentions)
    all_mean  = statistics.mean(all_densities)
    all_stdev = statistics.stdev(all_densities) if len(all_densities) > 1 else 1.0

    sorted_d = sorted(all_densities)
    n = len(sorted_d)
    pct = lambda p: sorted_d[min(int(p / 100 * n), n - 1)]

    print(f"  Общо документи:      {len(all_docs)}")
    print(f"  С AI mentions:       {len(densities)} ({len(densities)/len(all_docs)*100:.1f}%)")
    print(f"  Mean (с AI):         {corpus_mean:.4f} mentions/1000 words")
    print(f"  Mean (всички):       {all_mean:.4f}")
    print(f"  Stdev (всички):      {all_stdev:.4f}")
    print(f"  Median (с AI):       {corpus_median:.4f}")
    print(f"  P25: {pct(25):.4f}  P50: {pct(50):.4f}  P75: {pct(75):.4f}  P90: {pct(90):.4f}  P95: {pct(95):.4f}")

    # Quarterly trend
    quarterly = {}
    for doc in all_docs:
        q = doc["quarter"]
        if q not in quarterly:
            quarterly[q] = []
        quarterly[q].append(doc["ai_density"])

    quarterly_trend = []
    print("\n  Quarterly trend:")
    for q in sorted(quarterly.keys()):
        vals = quarterly[q]
        mean_d = statistics.mean(vals)
        quarterly_trend.append({
            "quarter":      q,
            "mean_density": round(mean_d, 4),
            "doc_count":    len(vals),
            "pct_with_ai":  round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        })
        print(f"    {q}: mean={mean_d:.4f}, n={len(vals)}, "
              f"with_ai={sum(1 for v in vals if v > 0)}/{len(vals)}")

    # Layer stats
    LAYERS = {
        "Chip Design":       ["NVDA", "AMD", "AVGO", "MRVL", "ARM", "QCOM"],
        "Semicon Equipment": ["ASML", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS"],
        "Memory":            ["MU", "WDC", "STX"],
        "Networking/Optics": ["ANET", "CIEN", "COHR", "LITE", "FN"],
        "Infrastructure":    ["VRT", "ETN", "DELL", "SMCI", "PWR"],
        "Hyperscalers":      ["MSFT", "GOOGL", "AMZN", "META", "ORCL"],
        "AI Software":       ["PLTR", "CRM", "NOW", "SNOW", "AI"],
    }
    SYM_TO_LAYER = {s: l for l, syms in LAYERS.items() for s in syms}

    layer_stats = {}
    for doc in all_docs:
        layer = SYM_TO_LAYER.get(doc["symbol"], "Other")
        if layer not in layer_stats:
            layer_stats[layer] = []
        layer_stats[layer].append(doc["ai_density"])

    layer_means = {}
    print("\n  Layer means:")
    for layer, vals in layer_stats.items():
        layer_means[layer] = round(statistics.mean(vals), 4)
        print(f"    {layer}: {layer_means[layer]:.4f} (n={len(vals)})")

    # Запази corpus_stats.json
    stats = {
        "generated_at":    datetime.now().isoformat() + "Z",
        "total_docs":      len(all_docs),
        "docs_with_ai":    len(densities),
        "pct_with_ai":     round(len(densities) / len(all_docs) * 100, 1),
        "corpus_mean":     round(corpus_mean, 6),
        "corpus_stdev":    round(corpus_stdev, 6),
        "corpus_median":   round(corpus_median, 6),
        "all_mean":        round(all_mean, 6),
        "all_stdev":       round(all_stdev, 6),
        "percentiles": {
            "p10": round(pct(10), 6),
            "p25": round(pct(25), 6),
            "p50": round(pct(50), 6),
            "p75": round(pct(75), 6),
            "p90": round(pct(90), 6),
            "p95": round(pct(95), 6),
            "p99": round(pct(99), 6),
        },
        "quarterly_trend": quarterly_trend,
        "layer_means":     layer_means,
        "all_docs":        all_docs,
    }

    out_path = DATA_DIR / "corpus_stats.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n→ corpus_stats.json: {len(all_docs)} документа")
    print(f"→ Raw текстове: {len(list(RAW_DIR.glob('*.txt')))} файла в {RAW_DIR}")
    print("✓ Готово!")


if __name__ == "__main__":
    main()
