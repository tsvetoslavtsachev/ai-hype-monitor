"""
analyze_rhetoric.py — AI Hype Monitor · NLP Модул
==================================================
Анализира SEC 8-K filings за AI rhetoric:
  1. Keyword Density Score — колко AI термини на 1000 думи
  2. Substance Ratio — AI термини до финансови термини (по-висок = по-конкретно)
  3. Uncertainty Ratio — AI термини до неопределени изрази (по-висок = повече hype)
  4. Rhetoric Score (0-100) — композитен показател за AI hype в отчетите

Изходен файл: app/data/rhetoric.json
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Пътища ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG_DIR = ROOT / "config"
APP_DATA_DIR = ROOT / "app" / "data"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

SEC_FILINGS_FILE = APP_DATA_DIR / "sec_filings.json"
OUTPUT_FILE = APP_DATA_DIR / "rhetoric.json"
KEYWORDS_FILE = CONFIG_DIR / "keywords.json"


# ── Зареждане на речника ──────────────────────────────────────────────────────

def _load_keywords() -> dict:
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_patterns(terms: list[str]) -> list[re.Pattern]:
    """Компилира regex patterns за бързо търсене (case-insensitive)."""
    patterns = []
    for term in terms:
        # Escape специалните символи, добавяме word boundary само за кратки термини
        escaped = re.escape(term)
        if len(term) <= 3:
            pattern = re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        patterns.append((term, pattern))
    return patterns


# ── Анализ на текст ───────────────────────────────────────────────────────────

def _count_words(text: str) -> int:
    """Брой думи в текста."""
    return len(re.findall(r"\b\w+\b", text))


def _count_matches(text: str, patterns: list[tuple[str, re.Pattern]]) -> dict[str, int]:
    """Брои всички съвпадения за всеки термин."""
    counts = {}
    for term, pattern in patterns:
        matches = pattern.findall(text)
        if matches:
            counts[term] = len(matches)
    return counts


def _extract_context_snippets(text: str, patterns: list[tuple[str, re.Pattern]],
                               window: int = 100, max_snippets: int = 5) -> list[str]:
    """Извлича контекстни фрагменти около намерените термини."""
    snippets = []
    for term, pattern in patterns[:10]:  # Само първите 10 термина
        for match in pattern.finditer(text):
            if len(snippets) >= max_snippets:
                break
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            snippet = "..." + text[start:end].strip() + "..."
            snippets.append(snippet)
    return snippets[:max_snippets]


def analyze_text(text: str, keywords: dict) -> dict:
    """
    Анализира един текст и връща метрики.
    
    Returns:
        {
          "word_count": int,
          "ai_mentions": int,
          "ai_density": float,       # AI mentions per 1000 words
          "substance_ratio": float,  # AI mentions / substance mentions (>1 = more hype)
          "uncertainty_ratio": float,# AI mentions / uncertainty mentions (>1 = more hype)
          "rhetoric_score": float,   # 0-100 composite
          "top_ai_terms": dict,      # term -> count
          "snippets": list[str],
        }
    """
    if not text or len(text) < 100:
        return {
            "word_count": 0, "ai_mentions": 0, "ai_density": 0,
            "substance_ratio": None, "uncertainty_ratio": None,
            "rhetoric_score": None, "top_ai_terms": {}, "snippets": [],
        }

    # Компилираме patterns
    ai_patterns = _build_patterns(keywords["ai_hype_terms"])
    substance_patterns = _build_patterns(keywords["substance_terms"])
    uncertainty_patterns = _build_patterns(keywords["uncertainty_terms"])

    word_count = _count_words(text)
    if word_count == 0:
        return {
            "word_count": 0, "ai_mentions": 0, "ai_density": 0,
            "substance_ratio": None, "uncertainty_ratio": None,
            "rhetoric_score": None, "top_ai_terms": {}, "snippets": [],
        }

    # Броим съвпадения
    ai_counts = _count_matches(text, ai_patterns)
    substance_counts = _count_matches(text, substance_patterns)
    uncertainty_counts = _count_matches(text, uncertainty_patterns)

    total_ai = sum(ai_counts.values())
    total_substance = sum(substance_counts.values())
    total_uncertainty = sum(uncertainty_counts.values())

    # AI Density: AI mentions per 1000 words
    ai_density = round(total_ai / word_count * 1000, 2)

    # Substance Ratio: колко AI mentions на 1 substance mention
    # Висок = повече hype (много AI talk, малко финансови детайли)
    substance_ratio = round(total_ai / max(total_substance, 1), 3)

    # Uncertainty Ratio: AI mentions vs uncertainty terms
    # Висок = повече "exploring/potential/could" около AI = hype
    uncertainty_ratio = round(total_ai / max(total_uncertainty, 1), 3)

    # Rhetoric Score (0-100):
    # Компонент 1: AI Density (нормализиран — 10 mentions/1000 words = 50 точки)
    density_score = min(100, ai_density * 5)

    # Компонент 2: Substance Ratio (>2 = hype, <0.5 = substance)
    # Нормализираме: ratio 0 = 0 точки, ratio 3+ = 100 точки
    substance_score = min(100, substance_ratio * 33)

    # Компонент 3: Uncertainty Ratio (>2 = hype)
    uncertainty_score = min(100, uncertainty_ratio * 33)

    # Composite: 50% density + 30% substance + 20% uncertainty
    rhetoric_score = round(
        density_score * 0.50 +
        substance_score * 0.30 +
        uncertainty_score * 0.20,
        1
    )

    # Топ AI термини
    top_ai = dict(sorted(ai_counts.items(), key=lambda x: x[1], reverse=True)[:10])

    # Контекстни фрагменти
    snippets = _extract_context_snippets(text, ai_patterns[:5])

    return {
        "word_count": word_count,
        "ai_mentions": total_ai,
        "substance_mentions": total_substance,
        "uncertainty_mentions": total_uncertainty,
        "ai_density": ai_density,
        "substance_ratio": substance_ratio,
        "uncertainty_ratio": uncertainty_ratio,
        "rhetoric_score": rhetoric_score,
        "top_ai_terms": top_ai,
        "snippets": snippets,
    }


# ── Агрегиране по компания и тримесечие ──────────────────────────────────────

def _quarter_from_date(d: str) -> str:
    """Преобразува дата в тримесечие: '2024-02-15' → 'Q1 2024'."""
    dt = datetime.strptime(d, "%Y-%m-%d")
    q = (dt.month - 1) // 3 + 1
    return f"Q{q} {dt.year}"


def _aggregate_company_rhetoric(filings: list[dict], keywords: dict) -> list[dict]:
    """Анализира всички filings на компания и агрегира по тримесечие."""
    quarterly = defaultdict(list)

    for filing in filings:
        text = filing.get("text", "")
        if not text:
            continue
        analysis = analyze_text(text, keywords)
        quarter = _quarter_from_date(filing["date"])
        quarterly[quarter].append({
            "date": filing["date"],
            "form": filing["form"],
            "accession": filing["accession"],
            **analysis,
        })

    result = []
    for quarter in sorted(quarterly.keys()):
        entries = quarterly[quarter]
        # Вземаме средните стойности за тримесечието
        def avg_field(field):
            vals = [e[field] for e in entries if e.get(field) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        result.append({
            "quarter": quarter,
            "filings_count": len(entries),
            "avg_ai_density": avg_field("ai_density"),
            "avg_rhetoric_score": avg_field("rhetoric_score"),
            "avg_substance_ratio": avg_field("substance_ratio"),
            "avg_uncertainty_ratio": avg_field("uncertainty_ratio"),
            "total_ai_mentions": sum(e.get("ai_mentions", 0) for e in entries),
            "filings": entries,
        })

    return result


# ── Исторически тренд (за Hype Index) ────────────────────────────────────────

def _build_sector_rhetoric_trend(all_companies: dict) -> list[dict]:
    """Изгражда тримесечен тренд за целия сектор."""
    quarter_data = defaultdict(list)

    for sym, company in all_companies.items():
        for q_entry in company.get("quarterly", []):
            if q_entry.get("avg_rhetoric_score") is not None:
                quarter_data[q_entry["quarter"]].append(q_entry["avg_rhetoric_score"])

    trend = []
    for quarter in sorted(quarter_data.keys()):
        scores = quarter_data[quarter]
        trend.append({
            "quarter": quarter,
            "sector_avg_rhetoric_score": round(sum(scores) / len(scores), 1),
            "companies_count": len(scores),
        })

    return trend


# ── Главна функция ────────────────────────────────────────────────────────────

def run(log=print) -> dict:
    """Анализира всички SEC filings и генерира rhetoric.json."""
    # Зареждаме речника
    keywords = _load_keywords()
    log(f"[analyze_rhetoric] Loaded {len(keywords['ai_hype_terms'])} AI terms, "
        f"{len(keywords['substance_terms'])} substance terms")

    # Зареждаме SEC filings
    if not SEC_FILINGS_FILE.exists():
        log("WARN: sec_filings.json не съществува — стартирайте fetch_sec_edgar.py първо")
        return {}

    with open(SEC_FILINGS_FILE, "r", encoding="utf-8") as f:
        filings_data = json.load(f)

    companies_raw = filings_data.get("companies", {})
    log(f"[analyze_rhetoric] Анализираме {len(companies_raw)} компании...")

    analyzed_companies = {}
    for sym, company in companies_raw.items():
        filings = company.get("filings", [])
        filings_with_text = [f for f in filings if f.get("text_fetched")]

        if not filings_with_text:
            log(f"  {sym:6s} — няма текстове за анализ")
            analyzed_companies[sym] = {
                "symbol": sym,
                "name": company["name"],
                "layer": company["layer"],
                "quarterly": [],
                "latest_rhetoric_score": None,
                "rhetoric_trend": "unknown",
            }
            continue

        quarterly = _aggregate_company_rhetoric(filings_with_text, keywords)

        # Тренд: сравняваме последните 2 тримесечия
        trend = "stable"
        if len(quarterly) >= 2:
            last = quarterly[-1]["avg_rhetoric_score"]
            prev = quarterly[-2]["avg_rhetoric_score"]
            if last and prev:
                delta = last - prev
                if delta > 5:
                    trend = "rising"
                elif delta < -5:
                    trend = "falling"

        latest_score = quarterly[-1]["avg_rhetoric_score"] if quarterly else None
        log(f"  {sym:6s} — {len(quarterly)} тримесечия, "
            f"последен score={latest_score}, тренд={trend}")

        analyzed_companies[sym] = {
            "symbol": sym,
            "name": company["name"],
            "layer": company["layer"],
            "quarterly": quarterly,
            "latest_rhetoric_score": latest_score,
            "rhetoric_trend": trend,
        }

    # Секторен тренд
    sector_trend = _build_sector_rhetoric_trend(analyzed_companies)
    log(f"[analyze_rhetoric] Секторен тренд: {len(sector_trend)} тримесечия")

    output = {
        "updated_at": date.today().isoformat(),
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "companies": analyzed_companies,
        "sector_trend": sector_trend,
        "meta": {
            "companies_analyzed": len(analyzed_companies),
            "companies_with_data": sum(
                1 for c in analyzed_companies.values() if c["latest_rhetoric_score"] is not None
            ),
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"[analyze_rhetoric] Written → {OUTPUT_FILE}")

    return output


if __name__ == "__main__":
    run()
