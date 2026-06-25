"""
calc_hype_index.py — AI Hype Monitor · Композитен Индекс
=========================================================
Изгражда AI Hype Score (0-100) от три компонента:

  1. Market Momentum (40%) — дневно
     - Среден 1Y percentile на AI акциите
     - Relative strength на AI сектора спрямо SPY
     
  2. Rhetoric Score (40%) — тримесечно (от SEC filings)
     - Средна плътност на AI термини в отчетите
     - Substance ratio (AI talk vs. финансови детайли)
     
  3. Valuation Stretch (20%) — дневно/седмично
     - Forward P/E на AI акциите спрямо историческа медиана
     - Концентрация на AI сектора в пазарната капитализация

Скала:
  0-30:   AI Winter (Депресия / Охлаждане)
  30-50:  Balanced (Рационален растеж)
  50-70:  Elevated (Повишена еуфория)
  70-85:  Hype (Силна еуфория)
  85-100: Bubble (Прегряване / Балон)

Изходни файлове:
  app/data/hype_index.json     — текущ snapshot + история
"""
from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yfinance as yf

# ── Пътища ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP_DATA_DIR = ROOT / "app" / "data"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

DAILY_PRICES_FILE = APP_DATA_DIR / "daily_prices.json"
RHETORIC_FILE = APP_DATA_DIR / "rhetoric.json"
OUTPUT_FILE = APP_DATA_DIR / "hype_index.json"

# История — натрупваме дневни точки
HISTORY_FILE = APP_DATA_DIR / "hype_history.json"


# ── Помощни функции ──────────────────────────────────────────────────────────

def _round(x, dp=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), dp)


def _clamp(x, lo=0.0, hi=100.0):
    if x is None:
        return None
    return max(lo, min(hi, x))


def _safe_avg(values: list) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


# ── Компонент 1: Market Momentum (40%) ───────────────────────────────────────

def _calc_market_momentum(prices_data: dict) -> dict:
    """
    Изчислява Market Momentum Score (0-100) от daily_prices.json.
    
    Логика:
    - Среден 1Y percentile на AI акциите (без benchmark)
      → 50th percentile = 50 точки (неутрален)
      → 90th percentile = 90 точки (силен momentum)
    - Relative strength: AI сектор vs SPY (1Y return)
      → AI outperforms SPY с 50%+ → добавя 20 точки
      → AI underperforms → намалява
    """
    stocks = prices_data.get("stocks", [])
    etfs = prices_data.get("etfs", [])
    benchmark = prices_data.get("benchmark", {})

    # Среден percentile на акциите
    stock_percentiles = [
        s["percentile_1y"] for s in stocks
        if s.get("percentile_1y") is not None and s.get("data_ok")
    ]
    avg_percentile = _safe_avg(stock_percentiles)

    # Relative strength: AI ETFs vs SPY
    spy_1y = benchmark.get("return_1y") if benchmark else None
    ai_etf_returns = [
        e["return_1y"] for e in etfs
        if e.get("return_1y") is not None and e.get("data_ok")
        and e["layer"] in ("Semiconductor", "AI Broad", "Cloud")
    ]
    avg_ai_etf_1y = _safe_avg(ai_etf_returns)

    # Relative strength score
    rel_strength_score = 50.0  # неутрален
    if avg_ai_etf_1y is not None and spy_1y is not None:
        outperformance = avg_ai_etf_1y - spy_1y
        # +50% outperformance → +25 точки; -50% → -25 точки
        rel_strength_score = _clamp(50 + outperformance * 0.5)

    # Momentum score = 70% percentile + 30% relative strength
    if avg_percentile is not None:
        momentum_score = avg_percentile * 0.70 + rel_strength_score * 0.30
    else:
        momentum_score = rel_strength_score

    return {
        "score": _round(_clamp(momentum_score)),
        "avg_percentile_1y": _round(avg_percentile, 1),
        "avg_ai_etf_return_1y": _round(avg_ai_etf_1y, 1),
        "spy_return_1y": _round(spy_1y, 1),
        "rel_strength_vs_spy": _round(
            avg_ai_etf_1y - spy_1y if avg_ai_etf_1y and spy_1y else None, 1
        ),
        "stocks_in_sample": len(stock_percentiles),
    }


# ── Компонент 2: Rhetoric Score (40%) ────────────────────────────────────────

def _calc_rhetoric_component(rhetoric_data: dict) -> dict:
    """
    Извлича Rhetoric Score от analyze_rhetoric.py output.
    
    Ако rhetoric_data е None (не е пуснат NLP анализ), използваме
    placeholder 50 (неутрален).
    """
    if not rhetoric_data:
        return {
            "score": 50.0,
            "source": "placeholder",
            "sector_avg_rhetoric": None,
            "companies_with_data": 0,
            "latest_quarter": None,
        }

    sector_trend = rhetoric_data.get("sector_trend", [])
    companies = rhetoric_data.get("companies", {})

    # Последното тримесечие
    latest_quarter = None
    sector_score = None
    if sector_trend:
        latest = sector_trend[-1]
        latest_quarter = latest["quarter"]
        sector_score = latest.get("sector_avg_rhetoric_score")

    # Ако нямаме секторен score, вземаме средно от компаниите
    if sector_score is None:
        company_scores = [
            c["latest_rhetoric_score"]
            for c in companies.values()
            if c.get("latest_rhetoric_score") is not None
        ]
        sector_score = _safe_avg(company_scores)

    # Нормализираме: rhetoric score вече е 0-100
    rhetoric_component_score = _clamp(sector_score) if sector_score else 50.0

    return {
        "score": _round(rhetoric_component_score),
        "source": "sec_edgar_nlp",
        "sector_avg_rhetoric": _round(sector_score, 1),
        "companies_with_data": rhetoric_data.get("meta", {}).get("companies_with_data", 0),
        "latest_quarter": latest_quarter,
    }


# ── Компонент 3: Valuation Stretch (20%) ─────────────────────────────────────

def _fetch_forward_pe(symbols: list[str], log=print) -> Optional[float]:
    """
    Взема Forward P/E от yfinance за списък от акции.
    Връща медианата.
    """
    pe_values = []
    for sym in symbols:
        try:
            info = yf.Ticker(sym).info
            fpe = info.get("forwardPE")
            if fpe and fpe > 0 and fpe < 500:  # Филтрираме аномалии
                pe_values.append(fpe)
            time.sleep(0.1)
        except Exception as e:
            log(f"  WARN PE {sym}: {e}")

    if not pe_values:
        return None

    # Медиана
    sorted_vals = sorted(pe_values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    return sorted_vals[n // 2]


# Исторически медиани на Forward P/E за AI сектора (базирани на Bloomberg/FactSet данни)
# Тези стойности са приблизителни исторически норми
HISTORICAL_PE_MEDIANS = {
    "Chip Design": 25.0,       # NVDA/AMD исторически норма (преди AI boom)
    "Semiconductor Equipment": 20.0,
    "Memory & Storage": 12.0,
    "Networking & Optics": 22.0,
    "Infrastructure & Power": 20.0,
    "Hyperscalers": 28.0,
    "AI Software": 35.0,
}
SECTOR_HISTORICAL_PE = 22.0   # Обща норма за tech


def _calc_valuation_stretch(prices_data: dict, log=print) -> dict:
    """
    Изчислява Valuation Stretch Score (0-100).
    
    Логика:
    - Взема Forward P/E на ключови AI акции
    - Сравнява с историческа норма
    - Stretch = (current_PE / historical_PE - 1) * 100
    - Нормализиране: 0% stretch = 50 точки; 100% stretch = 100 точки; -50% = 0 точки
    """
    # Ключови акции за PE оценка (само тези с надеждни PE данни)
    key_symbols = ["NVDA", "AMD", "AVGO", "MSFT", "META", "GOOGL", "AMAT", "ANET"]

    log(f"[valuation] Fetching Forward P/E for {len(key_symbols)} symbols...")
    median_pe = _fetch_forward_pe(key_symbols, log=log)

    if median_pe is None:
        return {
            "score": 50.0,
            "source": "unavailable",
            "median_forward_pe": None,
            "historical_pe_norm": SECTOR_HISTORICAL_PE,
            "pe_stretch_pct": None,
        }

    # PE Stretch %
    pe_stretch_pct = (median_pe / SECTOR_HISTORICAL_PE - 1) * 100

    # Нормализиране: 0% stretch = 50; 100% stretch = 100; -50% stretch = 0
    # Линейна функция: score = 50 + stretch_pct * 0.5
    valuation_score = _clamp(50 + pe_stretch_pct * 0.5)

    return {
        "score": _round(valuation_score),
        "source": "yfinance_forward_pe",
        "median_forward_pe": _round(median_pe, 1),
        "historical_pe_norm": SECTOR_HISTORICAL_PE,
        "pe_stretch_pct": _round(pe_stretch_pct, 1),
    }


# ── Съставяне на Composite Hype Score ────────────────────────────────────────

WEIGHTS = {
    "market_momentum": 0.40,
    "rhetoric": 0.40,
    "valuation": 0.20,
}

HYPE_ZONES = [
    (0, 30, "AI Winter", "❄️", "#3b82f6"),
    (30, 50, "Балансиран", "⚖️", "#22c55e"),
    (50, 70, "Повишен", "📈", "#eab308"),
    (70, 85, "Hype", "🔥", "#f97316"),
    (85, 100, "Балон", "💥", "#ef4444"),
]


def _classify_zone(score: float) -> dict:
    for lo, hi, label, icon, color in HYPE_ZONES:
        if lo <= score <= hi:
            return {"label": label, "icon": icon, "color": color, "range": [lo, hi]}
    return {"label": "Балон", "icon": "💥", "color": "#ef4444", "range": [85, 100]}


def _build_composite(momentum: dict, rhetoric: dict, valuation: dict) -> dict:
    """Изгражда финалния Composite Hype Score."""
    m_score = momentum.get("score") or 50.0
    r_score = rhetoric.get("score") or 50.0
    v_score = valuation.get("score") or 50.0

    composite = (
        m_score * WEIGHTS["market_momentum"] +
        r_score * WEIGHTS["rhetoric"] +
        v_score * WEIGHTS["valuation"]
    )
    composite = _clamp(composite)

    return {
        "score": _round(composite),
        "zone": _classify_zone(composite),
        "components": {
            "market_momentum": {**momentum, "weight": WEIGHTS["market_momentum"]},
            "rhetoric": {**rhetoric, "weight": WEIGHTS["rhetoric"]},
            "valuation": {**valuation, "weight": WEIGHTS["valuation"]},
        },
    }


# ── История ──────────────────────────────────────────────────────────────────

def _update_history(current_score: float, today: str) -> list[dict]:
    """Добавя текущия score към историята."""
    history = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    # Проверяваме дали вече имаме запис за днес
    existing = next((h for h in history if h["date"] == today), None)
    if existing:
        existing["score"] = current_score
    else:
        history.append({"date": today, "score": current_score})

    # Запазваме само последните 3 години (750 trading days)
    history = sorted(history, key=lambda x: x["date"])[-750:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

    return history


# ── Главна функция ────────────────────────────────────────────────────────────

def run(skip_valuation_pe: bool = False, log=print) -> dict:
    """Изгражда hype_index.json."""
    today = date.today().isoformat()

    # Зареждаме данните
    prices_data = {}
    if DAILY_PRICES_FILE.exists():
        with open(DAILY_PRICES_FILE, "r", encoding="utf-8") as f:
            prices_data = json.load(f)
    else:
        log("WARN: daily_prices.json не съществува — стартирайте fetch_prices.py първо")

    rhetoric_data = None
    if RHETORIC_FILE.exists():
        with open(RHETORIC_FILE, "r", encoding="utf-8") as f:
            rhetoric_data = json.load(f)
    else:
        log("INFO: rhetoric.json не съществува — ще използваме placeholder 50")

    # Изчисляваме компонентите
    log("[hype_index] Компонент 1: Market Momentum...")
    momentum = _calc_market_momentum(prices_data)
    log(f"  → Score: {momentum['score']} | Avg Percentile: {momentum['avg_percentile_1y']}")

    log("[hype_index] Компонент 2: Rhetoric...")
    rhetoric = _calc_rhetoric_component(rhetoric_data)
    log(f"  → Score: {rhetoric['score']} | Source: {rhetoric['source']}")

    log("[hype_index] Компонент 3: Valuation Stretch...")
    if skip_valuation_pe:
        valuation = {"score": 50.0, "source": "skipped"}
    else:
        valuation = _calc_valuation_stretch(prices_data, log=log)
    log(f"  → Score: {valuation['score']} | PE Stretch: {valuation.get('pe_stretch_pct')}%")

    # Composite
    composite = _build_composite(momentum, rhetoric, valuation)
    log(f"[hype_index] COMPOSITE SCORE: {composite['score']} — {composite['zone']['label']}")

    # История
    history = _update_history(composite["score"], today)

    # Изграждаме output
    output = {
        "updated_at": today,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hype_score": composite["score"],
        "zone": composite["zone"],
        "components": composite["components"],
        "history": history[-90:],    # Последните 90 дни за графиката
        "full_history_length": len(history),
        "interpretation": _build_interpretation(composite),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"[hype_index] Written → {OUTPUT_FILE}")

    return output


def _build_interpretation(composite: dict) -> dict:
    """Генерира текстова интерпретация на индекса."""
    score = composite["score"]
    zone = composite["zone"]["label"]
    m = composite["components"]["market_momentum"]
    r = composite["components"]["rhetoric"]
    v = composite["components"]["valuation"]

    signals = []

    # Momentum сигнали
    if m.get("avg_percentile_1y") and m["avg_percentile_1y"] > 80:
        signals.append("Акциите от AI веригата се търгуват близо до 1-годишните си върхове")
    elif m.get("avg_percentile_1y") and m["avg_percentile_1y"] < 30:
        signals.append("Акциите от AI веригата са под значителен натиск")

    if m.get("rel_strength_vs_spy") and m["rel_strength_vs_spy"] > 30:
        signals.append(f"AI секторът изпреварва S&P 500 с {m['rel_strength_vs_spy']}% за последната година")

    # Rhetoric сигнали
    if r.get("sector_avg_rhetoric") and r["sector_avg_rhetoric"] > 60:
        signals.append("Директорите говорят активно за AI в отчетите — висока плътност на AI термини")
    elif r.get("source") == "placeholder":
        signals.append("Rhetoric компонентът изчаква следващия earnings сезон")

    # Valuation сигнали
    if v.get("pe_stretch_pct") and v["pe_stretch_pct"] > 50:
        signals.append(f"Forward P/E е {v['pe_stretch_pct']}% над историческата норма")
    elif v.get("pe_stretch_pct") and v["pe_stretch_pct"] < 0:
        signals.append("Оценките са под историческата норма — потенциална корекция")

    return {
        "zone_description": {
            "AI Winter": "Секторът е в охлаждане. Инвеститорите са разочаровани от AI резултатите.",
            "Балансиран": "Пазарът оценява AI реалистично. Растежът е подкрепен от фундаменти.",
            "Повишен": "Оптимизмът расте. Внимавайте за разминаване между очаквания и резултати.",
            "Hype": "Еуфорията доминира. Оценките изпреварват фундаментите. Висок риск.",
            "Балон": "Класически балон. Историята показва, че такива нива предшестват корекции.",
        }.get(zone, ""),
        "key_signals": signals,
    }


if __name__ == "__main__":
    run()
