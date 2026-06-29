"""
calc_hype_history.py
====================
Изчислява историческия AI Hype Index и генерира JSON файловете за дашборда.

Използва:
  - app/data/price_history.json  (от backfill_prices.py)
  - app/data/rhetoric.json       (от score_rhetoric.py — новия scorer)

Генерира:
  - app/data/hype_index.json     (текущ score + история)
  - app/data/daily_prices.json   (цени + percentiles за дашборда)

Fix: Rhetoric score за текущото тримесечие използва ПОСЛЕДНОТО ЗАВЪРШЕНО
     тримесечие с данни (не нулира при нов Q).
"""

import json
import statistics
from datetime import datetime, date
from pathlib import Path

# ── Пътища ───────────────────────────────────────────────────────────────

DATA_DIR     = Path("app/data")
PRICE_HIST   = DATA_DIR / "price_history.json"
RHETORIC_IN  = DATA_DIR / "rhetoric.json"       # новия scorer output
OUT_HYPE_IDX = DATA_DIR / "hype_index.json"
OUT_DAILY    = DATA_DIR / "daily_prices.json"

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

ETF_NAMES = {
    "SMH":  "VanEck Semiconductor ETF",
    "SOXX": "iShares Semiconductor ETF",
    "AIQ":  "Global X AI & Technology ETF",
    "BOTZ": "Global X Robotics & AI ETF",
    "ROBO": "ROBO Global Robotics ETF",
    "ARKK": "ARK Innovation ETF",
    "WCLD": "WisdomTree Cloud Computing ETF",
    "CLOU": "Global X Cloud Computing ETF",
    "QQQ":  "Invesco QQQ Trust",
    "SPY":  "SPDR S&P 500 ETF",
    "XLK":  "Technology Select Sector SPDR",
}

ALL_STOCKS     = [s for stocks in LAYERS.values() for s in stocks]
SYMBOL_TO_LAYER = {s: layer for layer, symbols in LAYERS.items() for s in symbols}

# ── Зони ─────────────────────────────────────────────────────────────────

ZONES = {
    "AI Winter":    {"label": "AI Winter",       "color": "#3b82f6", "icon": "❄️"},
    "Cooling":      {"label": "Охлаждане",       "color": "#22c55e", "icon": "🌡️"},
    "Neutral":      {"label": "Балансиран",      "color": "#eab308", "icon": "⚖️"},
    "Hype":         {"label": "Повишен Hype",    "color": "#f97316", "icon": "🔥"},
    "Extreme Hype": {"label": "Балон",           "color": "#ef4444", "icon": "🚨"},
}

ZONE_DESCRIPTIONS = {
    "AI Winter":    "Пазарът е в охлаждане — AI акциите са близо до 52-седмичните си дъна.",
    "Cooling":      "Ентусиазмът намалява. Оценките се нормализират, rhetoric в отчетите се успокоява.",
    "Neutral":      "Балансирано състояние — реалистични очаквания, умерен растеж, без крайности.",
    "Hype":         "Повишен ентусиазъм. AI buzz в отчетите расте, оценките са над средните нива.",
    "Extreme Hype": "Признаци на балон. Оценките са исторически високи, rhetoric е максимален, momentum е на върха.",
}

# ── Помощни функции ───────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data, indent=2):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

def hype_zone_key(score: float) -> str:
    if score >= 80: return "Extreme Hype"
    if score >= 65: return "Hype"
    if score >= 45: return "Neutral"
    if score >= 30: return "Cooling"
    return "AI Winter"

def quarter_to_end_date(q: str) -> str:
    """'Q2 2023' → '2023-06-30'"""
    parts = q.split()
    qn, yr = int(parts[0][1]), int(parts[1])
    end_month = qn * 3
    end_day   = {3: 31, 6: 30, 9: 30, 12: 31}[end_month]
    return f"{yr}-{end_month:02d}-{end_day:02d}"

def quarter_sort_key(q: str) -> tuple:
    parts = q.split()
    return (int(parts[1]), int(parts[0][1]))

def get_percentile_at_or_before(prices: list, target_date: str) -> float | None:
    result = None
    for p in prices:
        if p["date"] <= target_date:
            result = p.get("percentile_1y")
        else:
            break
    return result

def calc_return(prices: list, days: int) -> float | None:
    if not prices or len(prices) < 2:
        return None
    latest = prices[-1]["close"]
    idx = max(0, len(prices) - days - 1)
    past = prices[idx]["close"]
    if past and past > 0:
        return round((latest / past - 1) * 100, 2)
    return None

def calc_drawdown(prices: list, lookback: int = 252) -> float | None:
    if not prices:
        return None
    recent = prices[-lookback:] if len(prices) >= lookback else prices
    high = max(p["close"] for p in recent)
    latest = prices[-1]["close"]
    if high > 0:
        return round((latest / high - 1) * 100, 2)
    return None

# ── Momentum Score ────────────────────────────────────────────────────────

def compute_momentum_score(price_data: dict, quarter_end: str) -> float:
    percentiles = []
    for symbol in ALL_STOCKS:
        if symbol not in price_data.get("stocks", {}):
            continue
        prices = price_data["stocks"][symbol]["prices"]
        pct = get_percentile_at_or_before(prices, quarter_end)
        if pct is not None:
            percentiles.append(pct)
    return round(statistics.mean(percentiles), 1) if percentiles else 50.0

# ── Rhetoric Score (от новия scorer) ─────────────────────────────────────

def compute_rhetoric_score_from_new(rhetoric_data: dict, quarter: str) -> float:
    """
    Взима rhetoric score за даденото тримесечие от новия scorer.
    Ако тримесечието няма данни (напр. текущото Q), използва
    ПОСЛЕДНОТО ЗАВЪРШЕНО тримесечие с поне 5 компании.
    """
    sector_quarterly = rhetoric_data.get("sector_quarterly", [])

    # Директно търсене
    for sq in sector_quarterly:
        if sq["quarter"] == quarter and sq["doc_count"] >= 5:
            return sq["mean_score"]

    # Fallback: последното тримесечие с поне 5 компании
    valid = [sq for sq in sector_quarterly if sq["doc_count"] >= 5]
    if valid:
        valid_sorted = sorted(valid, key=lambda x: quarter_sort_key(x["quarter"]))
        return valid_sorted[-1]["mean_score"]

    return 50.0  # default neutral

# ── Valuation Score ───────────────────────────────────────────────────────

def compute_valuation_score(price_data: dict, quarter_end: str) -> float:
    etf_percentiles = []
    for etf in ["SMH", "SOXX", "AIQ", "BOTZ"]:
        if etf not in price_data.get("etfs", {}):
            continue
        pct = get_percentile_at_or_before(price_data["etfs"][etf], quarter_end)
        if pct is not None:
            etf_percentiles.append(pct)
    return round(statistics.mean(etf_percentiles), 1) if etf_percentiles else 50.0

# ── Composite Hype Index ──────────────────────────────────────────────────

def compute_composite(momentum: float, rhetoric: float, valuation: float) -> float:
    return round(momentum * 0.40 + rhetoric * 0.35 + valuation * 0.25, 1)

# ── Тримесечна история ────────────────────────────────────────────────────

def generate_quarterly_history(price_data: dict, rhetoric_data: dict) -> list[dict]:
    quarters = []
    y, q = 2022, 4
    today = date.today()
    current_q = (today.month - 1) // 3 + 1
    while (y, q) <= (today.year, current_q):
        quarters.append(f"Q{q} {y}")
        q += 1
        if q > 4:
            q, y = 1, y + 1

    history = []
    for quarter in quarters:
        qend      = quarter_to_end_date(quarter)
        momentum  = compute_momentum_score(price_data, qend)
        rhetoric  = compute_rhetoric_score_from_new(rhetoric_data, quarter)
        valuation = compute_valuation_score(price_data, qend)
        composite = compute_composite(momentum, rhetoric, valuation)
        history.append({
            "quarter":    quarter,
            "date":       qend,
            "hype_index": composite,
            "zone":       hype_zone_key(composite),
            "components": {
                "momentum":  momentum,
                "rhetoric":  rhetoric,
                "valuation": valuation,
            },
        })
    return history

# ── hype_index.json (формат за app.js) ───────────────────────────────────

def build_hype_index_json(history: list, rhetoric_data: dict) -> dict:
    latest = history[-1] if history else {}
    prev   = history[-2] if len(history) >= 2 else {}

    score    = latest.get("hype_index", 0)
    zone_key = hype_zone_key(score)
    zone_obj = ZONES.get(zone_key, ZONES["Neutral"])
    comps    = latest.get("components", {})

    # Топ сигнали от новия rhetoric scorer
    signals = []
    companies = rhetoric_data.get("companies", [])
    # Вземи топ 3 по score с rising trend
    rising = [c for c in companies if c.get("trend_4q", "").startswith("↑")]
    rising.sort(key=lambda x: x.get("score", 0), reverse=True)
    for c in rising[:3]:
        signals.append(f"{c['symbol']} — AI rhetoric ↑ ({c['score']:.0f}/100)")

    # Momentum сигнал
    mom = comps.get("momentum", 50)
    if mom >= 75:
        signals.append(f"Пазарен momentum: {mom:.0f}/100 — AI акциите са близо до върховете")
    elif mom <= 30:
        signals.append(f"Пазарен momentum: {mom:.0f}/100 — AI акциите са близо до дъната")

    # Rhetoric сигнал
    rhet = comps.get("rhetoric", 50)
    if rhet >= 65:
        signals.append(f"Sector rhetoric: {rhet:.0f}/100 — AI buzz в отчетите е висок")

    return {
        "hype_score": score,
        "zone": zone_obj,
        "components": {
            "market_momentum": {
                "score":       comps.get("momentum", 0),
                "label":       "Пазарен Momentum",
                "description": "Среден 1Y процентил на AI акциите",
                "weight":      40,
            },
            "rhetoric": {
                "score":       comps.get("rhetoric", 0),
                "label":       "Rhetoric (Отчети)",
                "description": "AI keyword density в SEC 8-K filings (Z-score нормализиран)",
                "weight":      35,
            },
            "valuation": {
                "score":       comps.get("valuation", 0),
                "label":       "Оценки (Percentile)",
                "description": "Среден 1Y процентил на AI ETF-ите",
                "weight":      25,
            },
        },
        "interpretation": {
            "zone_description": ZONE_DESCRIPTIONS.get(zone_key, ""),
            "key_signals":      signals[:4],
        },
        "quarter":    latest.get("quarter", ""),
        "prev_score": prev.get("hype_index", 0),
        "change":     round(score - prev.get("hype_index", 0), 1),
        "updated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "history": [
            {"date": h["date"], "score": h["hype_index"], "quarter": h["quarter"]}
            for h in history
        ],
    }

# ── daily_prices.json (формат за app.js) ─────────────────────────────────

def build_daily_prices_json(price_data: dict) -> dict:
    stocks_list = []
    for symbol, data in price_data.get("stocks", {}).items():
        prices = data.get("prices", [])
        if not prices:
            continue
        latest = prices[-1]
        stocks_list.append({
            "symbol":        symbol,
            "name":          data.get("name", symbol),
            "layer":         data.get("layer", SYMBOL_TO_LAYER.get(symbol, "Other")),
            "price":         round(latest["close"], 2),
            "return_1d":     calc_return(prices, 1),
            "return_1m":     calc_return(prices, 21),
            "return_3m":     calc_return(prices, 63),
            "return_1y":     calc_return(prices, 252),
            "percentile_1y": latest.get("percentile_1y"),
            "drawdown_1y":   calc_drawdown(prices, 252),
            "date":          latest["date"],
        })

    etfs_list = []
    benchmark = None
    for etf, prices in price_data.get("etfs", {}).items():
        if not prices:
            continue
        latest = prices[-1]
        entry = {
            "symbol":        etf,
            "name":          ETF_NAMES.get(etf, etf),
            "price":         round(latest["close"], 2),
            "return_1d":     calc_return(prices, 1),
            "return_1m":     calc_return(prices, 21),
            "return_3m":     calc_return(prices, 63),
            "return_1y":     calc_return(prices, 252),
            "percentile_1y": latest.get("percentile_1y"),
            "drawdown_1y":   calc_drawdown(prices, 252),
            "date":          latest["date"],
        }
        if etf == "SPY":
            benchmark = entry
        else:
            etfs_list.append(entry)

    return {
        "generated_at": datetime.now().isoformat() + "Z",
        "stocks":    stocks_list,
        "etfs":      etfs_list,
        "benchmark": benchmark,
        "layers":    LAYERS,
    }

# ── Главна функция ────────────────────────────────────────────────────────

def main():
    print("=== AI Hype Monitor — Historical Index Calculator v2 ===", flush=True)

    price_data    = load_json(PRICE_HIST)
    rhetoric_data = load_json(RHETORIC_IN)

    print(f"Цени: {len(price_data.get('stocks', {}))} акции, {len(price_data.get('etfs', {}))} ETF-и", flush=True)
    print(f"Rhetoric: {len(rhetoric_data.get('companies', []))} компании, "
          f"{len(rhetoric_data.get('sector_quarterly', []))} тримесечия", flush=True)

    # Тримесечна история
    print("\nИзчисляване на историческия Hype Index...", flush=True)
    history = generate_quarterly_history(price_data, rhetoric_data)

    for h in history:
        c = h["components"]
        print(f"  {h['quarter']:10s}  composite={h['hype_index']:.1f}  "
              f"mom={c['momentum']:.1f}  rhet={c['rhetoric']:.1f}  val={c['valuation']:.1f}  "
              f"zone={h['zone']}", flush=True)

    # hype_index.json
    hype_idx = build_hype_index_json(history, rhetoric_data)
    save_json(OUT_HYPE_IDX, hype_idx)
    print(f"\n→ {OUT_HYPE_IDX}: score={hype_idx['hype_score']}, зона={hype_idx['zone']['label']}", flush=True)

    # daily_prices.json
    daily = build_daily_prices_json(price_data)
    save_json(OUT_DAILY, daily)
    print(f"→ {OUT_DAILY}: {len(daily['stocks'])} акции, {len(daily['etfs'])} ETF-и", flush=True)

    print("\n✓ Готово!")


if __name__ == "__main__":
    main()
