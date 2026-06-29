"""
score_rhetoric.py
=================
Изчислява нормализирани Rhetoric Scores (0-100) за всяка компания
и тримесечие, използвайки корпусната базова линия от corpus_stats.json.

Методология:
  1. Z-score = (company_density - corpus_mean) / corpus_stdev
  2. Нормализация към 0-100 чрез logistic функция (sigmoid)
     score = 100 / (1 + exp(-k * z_score))
     k=0.8 дава добро разпределение за нашия корпус
  3. Substance Bonus: ако substance_ratio > corpus_median → +5 точки
  4. Substance Penalty: ако ai_density > P75 но substance_ratio < 0.1 → -5 точки
     (много buzz, почти никаква конкретика = AI-washing)

Изход:
  - app/data/rhetoric.json      → за дашборда
  - app/data/rhetoric_history.json → исторически trend по тримесечия
"""

import json
import math
import statistics
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("app/data")

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

COMPANY_NAMES = {
    "NVDA": "Nvidia", "AMD": "AMD", "AVGO": "Broadcom", "MRVL": "Marvell",
    "ARM": "ARM Holdings", "QCOM": "Qualcomm", "ASML": "ASML", "AMAT": "Applied Materials",
    "LRCX": "Lam Research", "KLAC": "KLA Corp", "SNPS": "Synopsys", "CDNS": "Cadence",
    "MU": "Micron", "WDC": "Western Digital", "STX": "Seagate", "ANET": "Arista Networks",
    "CIEN": "Ciena", "COHR": "Coherent", "LITE": "Lumentum", "FN": "Fabrinet",
    "VRT": "Vertiv", "ETN": "Eaton", "DELL": "Dell", "SMCI": "Super Micro", "PWR": "Quanta",
    "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon", "META": "Meta",
    "ORCL": "Oracle", "PLTR": "Palantir", "CRM": "Salesforce", "NOW": "ServiceNow",
    "SNOW": "Snowflake", "AI": "C3.ai",
}


def sigmoid_score(z: float, k: float = 0.8) -> float:
    """Преобразува Z-score в 0-100 чрез sigmoid функция."""
    return round(100 / (1 + math.exp(-k * z)), 1)


def quarter_sort_key(q: str) -> tuple:
    """Сортира тримесечия като 'Q1 2023' → (2023, 1)."""
    parts = q.split()
    if len(parts) == 2:
        return (int(parts[1]), int(parts[0][1]))
    return (0, 0)


def main():
    print("=== Rhetoric Scorer v2 — Corpus-based Normalization ===", flush=True)

    # Зареди корпусна статистика
    stats_path = DATA_DIR / "corpus_stats.json"
    if not stats_path.exists():
        print("ГРЕШКА: corpus_stats.json не съществува. Пусни build_corpus.py първо.")
        return

    with open(stats_path) as f:
        stats = json.load(f)

    corpus_mean  = stats["all_mean"]
    corpus_stdev = stats["all_stdev"]
    p75_density  = stats["percentiles"]["p75"]
    p50_density  = stats["percentiles"]["p50"]  # median
    all_docs     = stats["all_docs"]

    print(f"Корпус: {stats['total_docs']} документа", flush=True)
    print(f"Mean: {corpus_mean:.4f}, Stdev: {corpus_stdev:.4f}", flush=True)
    print(f"P50: {p50_density:.4f}, P75: {p75_density:.4f}", flush=True)

    # Substance median от корпуса
    substance_vals = [d["substance_ratio"] for d in all_docs if d["ai_mentions"] > 0]
    substance_median = statistics.median(substance_vals) if substance_vals else 0.2
    print(f"Substance median: {substance_median:.3f}", flush=True)
    print()

    # Групирай документи по компания
    by_symbol = {}
    for doc in all_docs:
        sym = doc["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(doc)

    # Изчисли scores за всяка компания
    company_scores = {}
    quarterly_sector = {}  # quarter → list of scores

    for sym, docs in sorted(by_symbol.items()):
        if not docs:
            continue

        quarterly_data = []
        for doc in sorted(docs, key=lambda d: d["filing_date"]):
            density  = doc["ai_density"]
            subst    = doc["substance_ratio"]
            quarter  = doc["quarter"]
            mentions = doc["ai_mentions"]

            # Z-score спрямо целия корпус
            z = (density - corpus_mean) / corpus_stdev if corpus_stdev > 0 else 0

            # Base score от sigmoid
            base_score = sigmoid_score(z)

            # Substance adjustment
            bonus = 0
            if mentions > 0:
                if subst > substance_median:
                    bonus = +5   # конкретика над медианата → бонус
                if density > p75_density and subst < 0.10:
                    bonus = -5   # много buzz, почти никаква конкретика → AI-washing penalty

            final_score = max(0, min(100, base_score + bonus))

            # Trend label
            trend = "→"
            if len(quarterly_data) >= 2:
                prev_score = quarterly_data[-1]["score"]
                if final_score > prev_score + 3:
                    trend = "↑"
                elif final_score < prev_score - 3:
                    trend = "↓"

            entry = {
                "quarter":         quarter,
                "filing_date":     doc["filing_date"],
                "ai_density":      round(density, 4),
                "ai_mentions":     mentions,
                "substance_ratio": round(subst, 3),
                "z_score":         round(z, 3),
                "base_score":      round(base_score, 1),
                "bonus":           bonus,
                "score":           round(final_score, 1),
                "trend":           trend,
            }
            quarterly_data.append(entry)

            # Добави към sector quarterly
            if quarter not in quarterly_sector:
                quarterly_sector[quarter] = []
            quarterly_sector[quarter].append(final_score)

        # Последно тримесечие с данни
        last = quarterly_data[-1] if quarterly_data else None
        prev = quarterly_data[-2] if len(quarterly_data) >= 2 else None

        # Trend спрямо 4 тримесечия назад
        trend_4q = "→"
        if len(quarterly_data) >= 5:
            score_now  = quarterly_data[-1]["score"]
            score_4q   = quarterly_data[-5]["score"]
            if score_now > score_4q + 5:
                trend_4q = "↑ rising"
            elif score_now < score_4q - 5:
                trend_4q = "↓ falling"
            else:
                trend_4q = "→ stable"

        company_scores[sym] = {
            "symbol":        sym,
            "name":          COMPANY_NAMES.get(sym, sym),
            "layer":         SYM_TO_LAYER.get(sym, "Other"),
            "last_quarter":  last["quarter"] if last else "N/A",
            "last_date":     last["filing_date"] if last else "N/A",
            "score":         last["score"] if last else 0.0,
            "prev_score":    prev["score"] if prev else None,
            "trend":         last["trend"] if last else "→",
            "trend_4q":      trend_4q,
            "ai_density":    last["ai_density"] if last else 0.0,
            "ai_mentions":   last["ai_mentions"] if last else 0,
            "substance_ratio": last["substance_ratio"] if last else 0.0,
            "z_score":       last["z_score"] if last else 0.0,
            "history":       quarterly_data,
            "doc_count":     len(docs),
        }

        print(f"[{sym:5s}] {COMPANY_NAMES.get(sym, sym):20s} "
              f"score={last['score'] if last else 0:.1f}  "
              f"z={last['z_score'] if last else 0:.2f}  "
              f"density={last['ai_density'] if last else 0:.3f}  "
              f"trend={trend_4q}", flush=True)

    # Sector quarterly trend
    sector_quarterly = []
    for q in sorted(quarterly_sector.keys(), key=quarter_sort_key):
        vals = quarterly_sector[q]
        sector_quarterly.append({
            "quarter":      q,
            "mean_score":   round(statistics.mean(vals), 1),
            "median_score": round(statistics.median(vals), 1),
            "doc_count":    len(vals),
        })

    # Сектор scores
    layer_scores = {}
    for sym, data in company_scores.items():
        layer = data["layer"]
        if layer not in layer_scores:
            layer_scores[layer] = []
        layer_scores[layer].append(data["score"])

    layer_summary = {}
    for layer, scores in layer_scores.items():
        layer_summary[layer] = {
            "mean_score":   round(statistics.mean(scores), 1),
            "max_score":    round(max(scores), 1),
            "min_score":    round(min(scores), 1),
            "company_count": len(scores),
        }

    # Текущ sector rhetoric score (среден от последните quarters)
    latest_quarters = sorted(quarterly_sector.keys(), key=quarter_sort_key)
    # Вземи последното тримесечие с поне 5 компании
    current_rhetoric_score = 50.0
    for q in reversed(latest_quarters):
        if len(quarterly_sector[q]) >= 5:
            current_rhetoric_score = round(statistics.mean(quarterly_sector[q]), 1)
            break

    # Запази rhetoric.json за дашборда
    rhetoric_out = {
        "generated_at":           datetime.now().isoformat() + "Z",
        "corpus_mean":            round(corpus_mean, 4),
        "corpus_stdev":           round(corpus_stdev, 4),
        "substance_median":       round(substance_median, 3),
        "current_rhetoric_score": current_rhetoric_score,
        "sector_quarterly":       sector_quarterly,
        "layer_summary":          layer_summary,
        "companies":              list(company_scores.values()),
    }

    out_path = DATA_DIR / "rhetoric.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rhetoric_out, f, ensure_ascii=False, indent=2)

    print()
    print(f"→ rhetoric.json: {len(company_scores)} компании")
    print(f"→ Current rhetoric score: {current_rhetoric_score}")
    print()
    print("Топ 10 по Rhetoric Score:")
    sorted_companies = sorted(company_scores.values(), key=lambda x: x["score"], reverse=True)
    for c in sorted_companies[:10]:
        print(f"  {c['symbol']:5s} {c['name']:20s} score={c['score']:.1f}  "
              f"density={c['ai_density']:.3f}  substance={c['substance_ratio']:.2f}  "
              f"layer={c['layer']}")

    print()
    print("Layer summary:")
    for layer, s in sorted(layer_summary.items(), key=lambda x: -x[1]["mean_score"]):
        print(f"  {layer:20s}: mean={s['mean_score']:.1f}  max={s['max_score']:.1f}")

    print()
    print("Quarterly sector trend:")
    for q in sector_quarterly:
        print(f"  {q['quarter']}: mean={q['mean_score']:.1f}  n={q['doc_count']}")

    print("\n✓ Готово!")


if __name__ == "__main__":
    main()
