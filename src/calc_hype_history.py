"""
calc_hype_history.py
====================
Изчислява историческия AI Hype Index от Q4 2022 до днес.

Компоненти (тегла):
  - Momentum Score (40%):  1Y процентил на AI акциите vs. S&P 500
  - Rhetoric Score (35%):  SEC EDGAR NLP анализ (от rhetoric_history.json)
  - Valuation Score (25%): Относителна оценка (P/S proxy) на AI vs. S&P

Изход:
  - app/data/hype_history.json   — тримесечна история
  - app/data/hype_index.json     — текущ snapshot (за gauge)
  - app/data/rhetoric.json       — rhetoric данни за дашборда (обновен)
  - app/data/daily_prices.json   — дневни данни за heatmap (обновен)
"""

import json
import statistics
from datetime import datetime, date
from pathlib import Path

# ── Пътища ───────────────────────────────────────────────────────────────

DATA_DIR        = Path("app/data")
PRICE_HIST      = DATA_DIR / "price_history.json"
RHETORIC_HIST   = DATA_DIR / "rhetoric_history.json"
OUT_HYPE_HIST   = DATA_DIR / "hype_history.json"
OUT_HYPE_IDX    = DATA_DIR / "hype_index.json"
OUT_RHETORIC    = DATA_DIR / "rhetoric.json"
OUT_DAILY       = DATA_DIR / "daily_prices.json"

# ── AI Value Chain слоеве ─────────────────────────────────────────────────

LAYERS = {
    "Chip Design":       ["NVDA", "AMD", "AVGO", "MRVL", "ARM", "QCOM"],
    "Semicon Equipment": ["ASML", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS"],
    "Memory":            ["MU", "WDC", "STX"],
    "Networking/Optics": ["ANET", "CIEN", "COHR", "LITE", "FN"],
    "Infrastructure":    ["VRT", "ETN", "DELL", "SMCI", "PWR"],
    "Hyperscalers":      ["MSFT", "GOOGL", "AMZN", "META", "ORCL"],
    "AI Software":       ["PLTR", "CRM", "NOW", "SNOW", "AI"],
}

# Всички AI акции (без ETF-и)
ALL_STOCKS = [s for stocks in LAYERS.values() for s in stocks]

# ── Помощни функции ───────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data, indent=None):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False,
                  indent=indent, separators=None if indent else (",", ":"))


def date_to_quarter(d: str) -> str:
    dt = datetime.strptime(d[:10], "%Y-%m-%d")
    q  = (dt.month - 1) // 3 + 1
    return f"Q{q} {dt.year}"


def quarter_to_date(q: str) -> str:
    """'Q2 2023' → последният ден на тримесечието"""
    parts = q.split()
    qn, yr = int(parts[0][1]), int(parts[1])
    end_month = qn * 3
    end_day   = {3: 31, 6: 30, 9: 30, 12: 31}[end_month]
    return f"{yr}-{end_month:02d}-{end_day:02d}"


def get_price_at_date(prices: list[dict], target_date: str) -> float | None:
    """Връща close цената на или преди target_date."""
    best = None
    for p in prices:
        if p["date"] <= target_date:
            best = p["close"]
        else:
            break
    return best


def get_percentile_at_date(prices: list[dict], target_date: str) -> float | None:
    """Връща 1Y percentile на или преди target_date."""
    best = None
    for p in prices:
        if p["date"] <= target_date:
            best = p.get("percentile_1y")
        else:
            break
    return best


# ── Momentum Score ────────────────────────────────────────────────────────

def compute_momentum_score(price_data: dict, quarter_end: str) -> float:
    """
    Средният 1Y процентил на AI акциите в края на тримесечието.
    Нормализиран: 0-100.
    """
    percentiles = []
    stocks = price_data.get("stocks", {})

    for symbol in ALL_STOCKS:
        if symbol not in stocks:
            continue
        prices = stocks[symbol]["prices"]
        pct = get_percentile_at_date(prices, quarter_end)
        if pct is not None:
            percentiles.append(pct)

    if not percentiles:
        return 50.0

    return round(statistics.mean(percentiles), 1)


# ── Rhetoric Score ────────────────────────────────────────────────────────

def compute_rhetoric_score(rhetoric_data: dict, quarter: str) -> float:
    """
    Средният rhetoric score на всички компании за дадено тримесечие.
    """
    scores = []
    for symbol, company in rhetoric_data.get("companies", {}).items():
        for q in company.get("quarters", []):
            if q["quarter"] == quarter:
                scores.append(q["rhetoric_score"])
                break

    if not scores:
        # Ако нямаме данни за тримесечието, интерполираме от sector_trend
        for st in rhetoric_data.get("sector_trend", []):
            if st["quarter"] == quarter:
                return st["sector_avg_rhetoric_score"]
        return 0.0

    return round(statistics.mean(scores), 1)


# ── Valuation Score (proxy) ───────────────────────────────────────────────

def compute_valuation_score(price_data: dict, quarter_end: str) -> float:
    """
    Proxy за valuation: среден процентил на AI ETF-ите (SMH, SOXX, AIQ)
    спрямо 1Y история. По-висок = по-скъпо = повече hype.
    """
    etf_percentiles = []
    etfs = price_data.get("etfs", {})

    for etf in ["SMH", "SOXX", "AIQ", "BOTZ"]:
        if etf not in etfs:
            continue
        pct = get_percentile_at_date(etfs[etf], quarter_end)
        if pct is not None:
            etf_percentiles.append(pct)

    if not etf_percentiles:
        return 50.0

    return round(statistics.mean(etf_percentiles), 1)


# ── Composite Hype Index ──────────────────────────────────────────────────

def compute_composite_hype(momentum: float, rhetoric: float, valuation: float) -> float:
    """
    Композитен AI Hype Index (0-100).
    Тегла: Momentum 40%, Rhetoric 35%, Valuation 25%.
    """
    # Rhetoric е в скала 0-100 (вече)
    # Momentum и Valuation са в скала 0-100 (процентили)
    composite = (momentum * 0.40 + rhetoric * 0.35 + valuation * 0.25)
    return round(composite, 1)


def hype_zone(score: float) -> str:
    if score >= 80:  return "Extreme Hype"
    if score >= 65:  return "Hype"
    if score >= 45:  return "Neutral"
    if score >= 30:  return "Cooling"
    return "AI Winter"


# ── Генериране на тримесечна история ─────────────────────────────────────

def generate_quarterly_history(price_data: dict, rhetoric_data: dict) -> list[dict]:
    """Генерира пълна тримесечна история от Q4 2022."""
    # Всички тримесечия от Q4 2022 до текущото
    quarters = []
    start_year, start_q = 2022, 4
    today = date.today()
    current_q = (today.month - 1) // 3 + 1
    current_year = today.year

    y, q = start_year, start_q
    while (y, q) <= (current_year, current_q):
        quarters.append(f"Q{q} {y}")
        q += 1
        if q > 4:
            q = 1
            y += 1

    history = []
    for quarter in quarters:
        qend = quarter_to_date(quarter)

        momentum   = compute_momentum_score(price_data, qend)
        rhetoric   = compute_rhetoric_score(rhetoric_data, quarter)
        valuation  = compute_valuation_score(price_data, qend)
        composite  = compute_composite_hype(momentum, rhetoric, valuation)

        history.append({
            "quarter":          quarter,
            "date":             qend,
            "hype_index":       composite,
            "zone":             hype_zone(composite),
            "components": {
                "momentum":   momentum,
                "rhetoric":   rhetoric,
                "valuation":  valuation,
            },
        })

    return history


# ── Генериране на daily_prices.json за heatmap ────────────────────────────

def generate_daily_prices(price_data: dict) -> dict:
    """
    Генерира daily_prices.json с последните данни за всяка акция.
    Използва се за heatmap в дашборда.
    """
    stocks_out = {}
    stocks = price_data.get("stocks", {})

    for symbol, data in stocks.items():
        prices = data["prices"]
        if not prices:
            continue

        latest = prices[-1]
        # Намери цената преди 1 година
        one_year_ago = prices[0]["date"]  # fallback
        target = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"
        for p in prices:
            if p["date"] >= target:
                one_year_ago = p["close"]
                break

        change_1y = round((latest["close"] / one_year_ago - 1) * 100, 1) if one_year_ago else 0

        # Намери 52-week high/low
        recent_prices = [p["close"] for p in prices[-252:]] if len(prices) >= 252 else [p["close"] for p in prices]
        high_52w = max(recent_prices)
        low_52w  = min(recent_prices)

        stocks_out[symbol] = {
            "symbol":         symbol,
            "name":           data["name"],
            "layer":          data["layer"],
            "close":          latest["close"],
            "date":           latest["date"],
            "percentile_1y":  latest.get("percentile_1y", 50),
            "change_1y_pct":  change_1y,
            "high_52w":       round(high_52w, 2),
            "low_52w":        round(low_52w, 2),
        }

    # ETF-и
    etfs_out = {}
    for etf, prices in price_data.get("etfs", {}).items():
        if not prices:
            continue
        latest = prices[-1]
        etfs_out[etf] = {
            "symbol":        etf,
            "close":         latest["close"],
            "date":          latest["date"],
            "percentile_1y": latest.get("percentile_1y", 50),
        }

    return {
        "generated_at": datetime.now().isoformat() + "Z",
        "stocks":       stocks_out,
        "etfs":         etfs_out,
        "layers":       LAYERS,
    }


# ── Генериране на rhetoric.json за дашборда ───────────────────────────────

def generate_rhetoric_dashboard(rhetoric_data: dict) -> dict:
    """Форматира rhetoric данните за дашборда."""
    companies_out = {}

    for symbol, company in rhetoric_data.get("companies", {}).items():
        quarters = company.get("quarters", [])
        companies_out[symbol] = {
            "symbol":                symbol,
            "name":                  company["name"],
            "latest_rhetoric_score": company.get("latest_rhetoric_score", 0),
            "rhetoric_trend":        company.get("rhetoric_trend", "stable"),
            "quarters":              quarters,
        }

    return {
        "generated_at":  datetime.now().isoformat() + "Z",
        "companies":     companies_out,
        "sector_trend":  rhetoric_data.get("sector_trend", []),
        "meta":          rhetoric_data.get("meta", {}),
    }


# ── Главна функция ────────────────────────────────────────────────────────

def main():
    print("=== AI Hype Monitor — Historical Index Calculator ===")

    # Зареди данните
    print("Зареждане на price_history.json...")
    price_data = load_json(PRICE_HIST)

    print("Зареждане на rhetoric_history.json...")
    rhetoric_data = load_json(RHETORIC_HIST)

    # Генерирай тримесечна история
    print("Изчисляване на историческия Hype Index...")
    history = generate_quarterly_history(price_data, rhetoric_data)

    # Запиши hype_history.json
    save_json(OUT_HYPE_HIST, {"history": history}, indent=2)
    print(f"  → {OUT_HYPE_HIST} ({len(history)} тримесечия)")

    # Генерирай текущ snapshot (hype_index.json)
    latest = history[-1] if history else {}
    prev   = history[-2] if len(history) >= 2 else {}

    # Намери топ сигнали
    signals = []
    companies = rhetoric_data.get("companies", {})
    rising = [(s, c["latest_rhetoric_score"]) for s, c in companies.items()
              if c.get("rhetoric_trend") == "rising"]
    rising.sort(key=lambda x: x[1], reverse=True)
    for sym, score in rising[:3]:
        signals.append(f"{sym} rhetoric ↑ ({score:.0f})")

    hype_snapshot = {
        "generated_at":   datetime.now().isoformat() + "Z",
        "current_score":  latest.get("hype_index", 0),
        "zone":           latest.get("zone", "Neutral"),
        "quarter":        latest.get("quarter", ""),
        "date":           latest.get("date", ""),
        "components": {
            "momentum":   latest.get("components", {}).get("momentum", 0),
            "rhetoric":   latest.get("components", {}).get("rhetoric", 0),
            "valuation":  latest.get("components", {}).get("valuation", 0),
        },
        "prev_score":     prev.get("hype_index", 0),
        "change":         round(latest.get("hype_index", 0) - prev.get("hype_index", 0), 1),
        "signals":        signals,
        "history":        [{"date": h["date"], "score": h["hype_index"],
                            "quarter": h["quarter"]} for h in history],
    }

    save_json(OUT_HYPE_IDX, hype_snapshot, indent=2)
    print(f"  → {OUT_HYPE_IDX} (current score: {hype_snapshot['current_score']})")

    # Генерирай daily_prices.json
    print("Генериране на daily_prices.json...")
    daily = generate_daily_prices(price_data)
    save_json(OUT_DAILY, daily, indent=2)
    print(f"  → {OUT_DAILY} ({len(daily['stocks'])} акции, {len(daily['etfs'])} ETF-и)")

    # Генерирай rhetoric.json
    print("Генериране на rhetoric.json...")
    rhetoric_dash = generate_rhetoric_dashboard(rhetoric_data)
    save_json(OUT_RHETORIC, rhetoric_dash, indent=2)
    print(f"  → {OUT_RHETORIC} ({len(rhetoric_dash['companies'])} компании)")

    # Обобщение
    print()
    print("=== Резултат ===")
    print(f"Период:       {history[0]['quarter']} → {history[-1]['quarter']}")
    print(f"Текущ score:  {hype_snapshot['current_score']} ({hype_snapshot['zone']})")
    print()
    print("Тримесечна история:")
    for h in history:
        bar = "█" * int(h["hype_index"] / 5)
        print(f"  {h['quarter']:8s}  {h['hype_index']:5.1f}  {bar:<20s}  {h['zone']}")


if __name__ == "__main__":
    main()
