"""
fetch_prices.py — AI Hype Monitor · Ценови Модул
=================================================
Чете дневни цени от price-archive (tsvetoslavtsachev/price-archive) за AI ETF-ите
и директно от yfinance за индивидуалните акции от AI Value Chain.

Изходен файл: app/data/daily_prices.json
Формат:
{
  "updated_at": "2026-06-26",
  "market_open": true,
  "etfs": [...],
  "stocks": [...],
  "layers": {...}
}
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

# ── Пътища ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG_DIR = ROOT / "config"
APP_DATA_DIR = ROOT / "app" / "data"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# price-archive може да е checkout-нато в CI или локално
PRICE_ARCHIVE_ROOT = Path(os.environ.get("PRICE_ARCHIVE_ROOT", ROOT.parent / "price-archive"))

# ── Константи ────────────────────────────────────────────────────────────────
LOOKBACK_DAYS = 400          # за 1Y percentile (252 trading days + buffer)
PERCENTILE_WINDOW = 252      # ~1 търговска година
BENCHMARK_SYMBOL = "SPY"
OUTPUT_FILE = APP_DATA_DIR / "daily_prices.json"

# AI ETF-и от price-archive (вече налични серии)
AI_ETFS = {
    "px_smh_daily":   {"symbol": "SMH",  "name": "VanEck Semiconductor",        "layer": "Semiconductor"},
    "px_soxx_daily":  {"symbol": "SOXX", "name": "iShares Semiconductor",        "layer": "Semiconductor"},
    "px_aiq_daily":   {"symbol": "AIQ",  "name": "Global X AI & Technology",     "layer": "AI Broad"},
    "px_botz_daily":  {"symbol": "BOTZ", "name": "Global X Robotics & AI",       "layer": "AI Broad"},
    "px_robo_daily":  {"symbol": "ROBO", "name": "ROBO Global Robotics",         "layer": "AI Broad"},
    "px_wcld_daily":  {"symbol": "WCLD", "name": "WisdomTree Cloud Computing",   "layer": "Cloud"},
    "px_clou_daily":  {"symbol": "CLOU", "name": "Global X Cloud Computing",     "layer": "Cloud"},
    "px_arkk_daily":  {"symbol": "ARKK", "name": "ARK Innovation",               "layer": "Disruptive"},
    "px_xlk_daily":   {"symbol": "XLK",  "name": "Technology Select",            "layer": "Broad Tech"},
    "px_qqq_daily":   {"symbol": "QQQ",  "name": "Invesco Nasdaq 100",           "layer": "Broad Tech"},
    "px_spy_daily":   {"symbol": "SPY",  "name": "S&P 500 (Benchmark)",          "layer": "Benchmark"},
}


# ── Помощни функции ──────────────────────────────────────────────────────────

def _round(x, dp=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), dp)


def _pct(x):
    return _round(x * 100, 2) if x is not None else None


def _percentile_rank(series: list[float], current: float) -> Optional[float]:
    """Процентил на текущата стойност спрямо историческата серия (0-100)."""
    if not series or current is None:
        return None
    below = sum(1 for v in series if v <= current)
    return _round(below / len(series) * 100, 1)


def _calc_return(prices: list[float], n_days: int) -> Optional[float]:
    """Процентна промяна за последните n_days."""
    if len(prices) < n_days + 1:
        return None
    end = prices[-1]
    start = prices[-n_days - 1]
    if start == 0:
        return None
    return _pct((end - start) / start)


def _calc_drawdown(prices: list[float]) -> Optional[float]:
    """Максимален drawdown от последния peak."""
    if not prices:
        return None
    peak = max(prices)
    current = prices[-1]
    if peak == 0:
        return None
    return _pct((current - peak) / peak)


# ── Четене от price-archive ──────────────────────────────────────────────────

def _read_archive_series(series_id: str, root: Path) -> list[dict]:
    """Чете year-partitioned JSONL серия от price-archive."""
    series_dir = root / "archive" / series_id
    if not series_dir.exists():
        return []
    records = {}
    for yfile in sorted(series_dir.glob("*.jsonl")):
        with open(yfile, "r", encoding="utf-8") as f:
            for raw in f:
                s = raw.strip()
                if not s:
                    continue
                rec = json.loads(s)
                ao = rec["as_of"]
                ro = rec.get("recorded_on", "")
                cur = records.get(ao)
                if cur is None or ro >= cur.get("recorded_on", ""):
                    records[ao] = rec
    return [records[k] for k in sorted(records)]


def _archive_to_prices(records: list[dict], since: str) -> list[tuple[str, float]]:
    """Филтрира записи след дата и връща (as_of, close) двойки."""
    return [
        (r["as_of"], r["value"])
        for r in records
        if r["as_of"] >= since
    ]


# ── Четене от yfinance (за акции извън price-archive) ────────────────────────

def _fetch_yfinance_prices(symbols: list[str], period: str = "2y") -> dict[str, list[tuple[str, float]]]:
    """Дърпа исторически цени за списък от тикъри."""
    if not symbols:
        return {}
    result = {}
    batch_size = 20
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            raw = yf.download(
                batch,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw.empty:
                continue
            close = raw["Close"] if "Close" in raw.columns else raw
            if isinstance(close, pd.Series):
                close = close.to_frame(name=batch[0])
            for sym in batch:
                if sym not in close.columns:
                    continue
                series = close[sym].dropna()
                result[sym] = [
                    (str(idx.date()), float(val))
                    for idx, val in series.items()
                ]
        except Exception as e:
            print(f"WARN yfinance batch {batch}: {e}", file=sys.stderr)
        time.sleep(0.5)
    return result


# ── Изграждане на запис за един инструмент ────────────────────────────────────

def _build_record(symbol: str, name: str, layer: str,
                  prices_ts: list[tuple[str, float]]) -> dict:
    """Изгражда пълен запис с метрики от ценова серия."""
    if not prices_ts:
        return {
            "symbol": symbol, "name": name, "layer": layer,
            "price": None, "price_date": None,
            "return_1d": None, "return_1m": None,
            "return_3m": None, "return_6m": None, "return_1y": None,
            "percentile_1y": None, "drawdown_1y": None,
            "high_1y": None, "low_1y": None,
            "data_ok": False,
        }

    # Вземаме само последните LOOKBACK_DAYS записа
    cutoff = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    filtered = [(d, p) for d, p in prices_ts if d >= cutoff]
    if not filtered:
        filtered = prices_ts[-LOOKBACK_DAYS:]

    dates = [d for d, _ in filtered]
    prices = [p for _, p in filtered]

    current_price = prices[-1]
    current_date = dates[-1]

    # Percentile: позиция на текущата цена в 1Y прозорец
    window = prices[-PERCENTILE_WINDOW:] if len(prices) >= PERCENTILE_WINDOW else prices
    pct_rank = _percentile_rank(window[:-1], current_price)  # exclude current

    # Returns
    r1d = _calc_return(prices, 1)
    r1m = _calc_return(prices, 21)
    r3m = _calc_return(prices, 63)
    r6m = _calc_return(prices, 126)
    r1y = _calc_return(prices, 252)

    # High/Low 1Y
    window_prices = prices[-PERCENTILE_WINDOW:]
    high_1y = _round(max(window_prices), 2)
    low_1y = _round(min(window_prices), 2)
    dd_1y = _pct((current_price - high_1y) / high_1y) if high_1y else None

    return {
        "symbol": symbol,
        "name": name,
        "layer": layer,
        "price": _round(current_price, 2),
        "price_date": current_date,
        "return_1d": r1d,
        "return_1m": r1m,
        "return_3m": r3m,
        "return_6m": r6m,
        "return_1y": r1y,
        "percentile_1y": pct_rank,
        "drawdown_1y": dd_1y,
        "high_1y": high_1y,
        "low_1y": low_1y,
        "data_ok": True,
    }


# ── Агрегиране по слоеве ──────────────────────────────────────────────────────

def _aggregate_layers(stocks: list[dict], universe_df: pd.DataFrame) -> dict:
    """Изчислява средни метрики по слой (layer)."""
    layers = {}
    stock_map = {s["symbol"]: s for s in stocks}

    for layer_name, group in universe_df.groupby("layer"):
        layer_stocks = [
            stock_map[sym]
            for sym in group["symbol"]
            if sym in stock_map and stock_map[sym]["data_ok"]
        ]
        if not layer_stocks:
            continue

        def avg(field):
            vals = [s[field] for s in layer_stocks if s[field] is not None]
            return _round(sum(vals) / len(vals), 1) if vals else None

        layers[layer_name] = {
            "name": layer_name,
            "count": len(layer_stocks),
            "avg_return_1d": avg("return_1d"),
            "avg_return_1m": avg("return_1m"),
            "avg_return_3m": avg("return_3m"),
            "avg_return_1y": avg("return_1y"),
            "avg_percentile_1y": avg("percentile_1y"),
            "layer_order": int(group["layer_order"].iloc[0]),
            "layer_weight": float(group["layer_weight"].iloc[0]),
        }

    return layers


# ── Главна функция ────────────────────────────────────────────────────────────

def run(price_archive_root: Optional[Path] = None, log=print) -> dict:
    """Основна функция — изгражда daily_prices.json."""
    archive_root = price_archive_root or PRICE_ARCHIVE_ROOT
    log(f"[fetch_prices] price-archive root: {archive_root}")

    # 1. Четем universe
    universe_df = pd.read_csv(CONFIG_DIR / "universe.csv")
    universe_df = universe_df[universe_df["enabled"] == 1].copy()
    stock_symbols = universe_df["symbol"].tolist()
    log(f"[fetch_prices] Universe: {len(stock_symbols)} stocks")

    # 2. ETF данни от price-archive
    since_date = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    etf_records = []
    for series_id, meta in AI_ETFS.items():
        raw = _read_archive_series(series_id, archive_root)
        pts = _archive_to_prices(raw, since_date)
        rec = _build_record(meta["symbol"], meta["name"], meta["layer"], pts)
        etf_records.append(rec)
        status = "OK" if rec["data_ok"] else "MISSING"
        log(f"  ETF {meta['symbol']:6s} [{status}] price={rec['price']} pct1y={rec['percentile_1y']}")

    # 3. Акции от yfinance (за цялата AI Value Chain)
    log(f"[fetch_prices] Fetching {len(stock_symbols)} stocks from yfinance...")
    yf_prices = _fetch_yfinance_prices(stock_symbols, period="2y")

    stock_records = []
    for _, row in universe_df.iterrows():
        sym = row["symbol"]
        pts = yf_prices.get(sym, [])
        rec = _build_record(sym, row["name"], row["layer"], pts)
        stock_records.append(rec)
        status = "OK" if rec["data_ok"] else "MISSING"
        log(f"  Stock {sym:6s} [{status}] price={rec['price']} pct1y={rec['percentile_1y']}")

    # 4. Агрегиране по слоеве
    layers = _aggregate_layers(stock_records, universe_df)

    # 5. Benchmark relative performance
    spy_rec = next((e for e in etf_records if e["symbol"] == "SPY"), None)

    # 6. Изграждаме изходния JSON
    output = {
        "updated_at": date.today().isoformat(),
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": spy_rec,
        "etfs": [e for e in etf_records if e["symbol"] != "SPY"],
        "stocks": stock_records,
        "layers": layers,
        "meta": {
            "stock_count": len(stock_records),
            "etf_count": len(etf_records) - 1,
            "stocks_ok": sum(1 for s in stock_records if s["data_ok"]),
            "etfs_ok": sum(1 for e in etf_records if e["data_ok"] and e["symbol"] != "SPY"),
        },
    }

    # 7. Записваме
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"[fetch_prices] Written → {OUTPUT_FILE}")

    return output


if __name__ == "__main__":
    run()
