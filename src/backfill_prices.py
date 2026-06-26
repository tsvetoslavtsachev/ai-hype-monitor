"""
backfill_prices.py
==================
Исторически backfill на цените за AI Value Chain от Q4 2022 до днес.

Логика:
  - ETF-и (SMH, SOXX, AIQ, BOTZ, ROBO, WCLD, CLOU, ARKK, SPY):
      четем от price-archive JSONL файловете
  - Индивидуални акции (NVDA, AMD, META, ...):
      теглим от yfinance

Изход: app/data/price_history.json
"""

import json
import os
import sys
import argparse
from datetime import date, datetime
from pathlib import Path

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("ERROR: pip install yfinance pandas")
    sys.exit(1)

# ── Конфигурация ──────────────────────────────────────────────────────────

START_DATE = "2022-10-01"   # Q4 2022
END_DATE   = date.today().isoformat()

# ETF-и, налични в price-archive (series_id → ticker)
ARCHIVE_ETFS = {
    "px_smh_daily":  "SMH",
    "px_soxx_daily": "SOXX",
    "px_aiq_daily":  "AIQ",
    "px_botz_daily": "BOTZ",
    "px_robo_daily": "ROBO",
    "px_wcld_daily": "WCLD",
    "px_clou_daily": "CLOU",
    "px_arkk_daily": "ARKK",
    "px_spy_daily":  "SPY",
    "px_qqq_daily":  "QQQ",
    "px_xlk_daily":  "XLK",
}

# Индивидуални акции — теглим от yfinance
STOCKS = {
    # Chip Design
    "NVDA":  {"name": "Nvidia",               "layer": "Chip Design"},
    "AMD":   {"name": "AMD",                   "layer": "Chip Design"},
    "AVGO":  {"name": "Broadcom",              "layer": "Chip Design"},
    "MRVL":  {"name": "Marvell Technology",    "layer": "Chip Design"},
    "ARM":   {"name": "ARM Holdings",          "layer": "Chip Design"},
    "QCOM":  {"name": "Qualcomm",              "layer": "Chip Design"},
    # Semiconductor Equipment
    "ASML":  {"name": "ASML Holding",          "layer": "Semicon Equipment"},
    "AMAT":  {"name": "Applied Materials",     "layer": "Semicon Equipment"},
    "LRCX":  {"name": "Lam Research",          "layer": "Semicon Equipment"},
    "KLAC":  {"name": "KLA Corp",              "layer": "Semicon Equipment"},
    "SNPS":  {"name": "Synopsys",              "layer": "Semicon Equipment"},
    "CDNS":  {"name": "Cadence Design",        "layer": "Semicon Equipment"},
    # Memory
    "MU":    {"name": "Micron Technology",     "layer": "Memory"},
    "WDC":   {"name": "Western Digital",       "layer": "Memory"},
    "STX":   {"name": "Seagate Technology",    "layer": "Memory"},
    # Networking / Optics
    "ANET":  {"name": "Arista Networks",       "layer": "Networking/Optics"},
    "CIEN":  {"name": "Ciena",                 "layer": "Networking/Optics"},
    "COHR":  {"name": "Coherent",              "layer": "Networking/Optics"},
    "LITE":  {"name": "Lumentum",              "layer": "Networking/Optics"},
    "FN":    {"name": "Fabrinet",              "layer": "Networking/Optics"},
    # Infrastructure
    "VRT":   {"name": "Vertiv Holdings",       "layer": "Infrastructure"},
    "ETN":   {"name": "Eaton Corp",            "layer": "Infrastructure"},
    "DELL":  {"name": "Dell Technologies",     "layer": "Infrastructure"},
    "SMCI":  {"name": "Super Micro Computer",  "layer": "Infrastructure"},
    "PWR":   {"name": "Quanta Services",       "layer": "Infrastructure"},
    # Hyperscalers
    "MSFT":  {"name": "Microsoft",             "layer": "Hyperscalers"},
    "GOOGL": {"name": "Alphabet",              "layer": "Hyperscalers"},
    "AMZN":  {"name": "Amazon",                "layer": "Hyperscalers"},
    "META":  {"name": "Meta Platforms",        "layer": "Hyperscalers"},
    "ORCL":  {"name": "Oracle",                "layer": "Hyperscalers"},
    # AI Software
    "PLTR":  {"name": "Palantir",              "layer": "AI Software"},
    "CRM":   {"name": "Salesforce",            "layer": "AI Software"},
    "NOW":   {"name": "ServiceNow",            "layer": "AI Software"},
    "SNOW":  {"name": "Snowflake",             "layer": "AI Software"},
    "AI":    {"name": "C3.ai",                 "layer": "AI Software"},
}

# ── Четене от price-archive ───────────────────────────────────────────────

def read_archive_series(archive_root: Path, series_id: str,
                         start: str, end: str) -> list[dict]:
    """Чете JSONL файлове от price-archive за даден series_id."""
    series_dir = archive_root / "archive" / series_id
    if not series_dir.exists():
        print(f"  [SKIP] {series_id} — не е намерен в archive")
        return []

    start_year = int(start[:4])
    end_year   = int(end[:4])
    records = []

    for year in range(start_year, end_year + 1):
        fpath = series_dir / f"{year}.jsonl"
        if not fpath.exists():
            continue
        with open(fpath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    as_of = rec.get("as_of", "")
                    if start <= as_of <= end:
                        records.append({
                            "date":  as_of,
                            "close": rec.get("close") or rec.get("value"),
                        })
                except json.JSONDecodeError:
                    continue

    records.sort(key=lambda x: x["date"])
    return records


# ── Изчисляване на 1Y процентил ───────────────────────────────────────────

def compute_percentile_series(prices: list[dict]) -> list[dict]:
    """
    За всеки ден изчислява процентила на close цената
    спрямо предходните 252 търговски дни (≈ 1 година).
    """
    if len(prices) < 2:
        return prices

    closes = [p["close"] for p in prices]
    result = []
    window = 252

    for i, p in enumerate(prices):
        if i < window:
            # Недостатъчно история — използваме наличното
            window_closes = closes[:i + 1]
        else:
            window_closes = closes[i - window: i + 1]

        c = p["close"]
        below = sum(1 for x in window_closes if x <= c)
        pct = round(below / len(window_closes) * 100, 1)
        result.append({**p, "percentile_1y": pct})

    return result


# ── Теглене от yfinance ───────────────────────────────────────────────────

def fetch_yfinance(symbol: str, start: str, end: str) -> list[dict]:
    """Тегли дневни цени от yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, auto_adjust=True)
        if df.empty:
            print(f"  [WARN] {symbol} — празен резултат от yfinance")
            return []
        records = []
        for idx, row in df.iterrows():
            d = idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10]
            records.append({
                "date":  d,
                "close": round(float(row["Close"]), 4),
            })
        records.sort(key=lambda x: x["date"])
        return records
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")
        return []


# ── Главна функция ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backfill AI Hype Monitor price history")
    parser.add_argument("--price-archive-root", default="../price-archive",
                        help="Път до price-archive repo")
    parser.add_argument("--output", default="app/data/price_history.json",
                        help="Изходен файл")
    parser.add_argument("--start", default=START_DATE)
    parser.add_argument("--end",   default=END_DATE)
    args = parser.parse_args()

    archive_root = Path(args.price_archive_root)
    output_path  = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== AI Hype Monitor — Price Backfill ===")
    print(f"Период: {args.start} → {args.end}")
    print(f"Archive root: {archive_root}")
    print()

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "start_date":   args.start,
        "end_date":     args.end,
        "etfs":   {},
        "stocks": {},
    }

    # ── ETF-и от price-archive ────────────────────────────────────────────
    print("--- ETF-и от price-archive ---")
    for series_id, ticker in ARCHIVE_ETFS.items():
        print(f"  {ticker} ({series_id})...", end=" ", flush=True)
        records = read_archive_series(archive_root, series_id, args.start, args.end)
        if records:
            records = compute_percentile_series(records)
            result["etfs"][ticker] = records
            print(f"OK ({len(records)} дни)")
        else:
            # Fallback към yfinance
            print(f"archive miss → yfinance...", end=" ", flush=True)
            records = fetch_yfinance(ticker, args.start, args.end)
            if records:
                records = compute_percentile_series(records)
                result["etfs"][ticker] = records
                print(f"OK ({len(records)} дни)")
            else:
                print("FAIL")

    print()

    # ── Индивидуални акции от yfinance ────────────────────────────────────
    print("--- Индивидуални акции от yfinance ---")
    for symbol, meta in STOCKS.items():
        print(f"  {symbol} ({meta['name']})...", end=" ", flush=True)
        records = fetch_yfinance(symbol, args.start, args.end)
        if records:
            records = compute_percentile_series(records)
            result["stocks"][symbol] = {
                "name":    meta["name"],
                "layer":   meta["layer"],
                "prices":  records,
            }
            print(f"OK ({len(records)} дни)")
        else:
            print("FAIL")

    # ── Статистика ────────────────────────────────────────────────────────
    etf_ok    = len(result["etfs"])
    stock_ok  = len(result["stocks"])
    total_ok  = etf_ok + stock_ok
    total_exp = len(ARCHIVE_ETFS) + len(STOCKS)

    result["meta"] = {
        "etfs_ok":    etf_ok,
        "stocks_ok":  stock_ok,
        "total_ok":   total_ok,
        "total_expected": total_exp,
    }

    # ── Запис ─────────────────────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = output_path.stat().st_size / 1024 / 1024
    print()
    print(f"=== Резултат ===")
    print(f"ETF-и:   {etf_ok}/{len(ARCHIVE_ETFS)}")
    print(f"Акции:   {stock_ok}/{len(STOCKS)}")
    print(f"Общо:    {total_ok}/{total_exp}")
    print(f"Файл:    {output_path} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
