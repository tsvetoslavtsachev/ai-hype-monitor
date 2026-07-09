"""
multiple_v2.py — Е-крак глас 3: оценъчен множител (Фаза 2, 2.3).
================================================================
Trailing P/S седмично: market cap (цена × shares, PIT) / TTM revenue (PIT
идентичност) per компания → МЕДИАНА по вселената → робастен z (разширяващ се,
min 52 седмици). Единственият непрекъснат глас (цените са дневни).

Ценови път (картографиран): v1 `app/data/prices/{TICKER}.json` (дневна серия
{date,close}, 2022-10..2026-06, 35/36 тикера) — ЗДРАВ. Тук е READ-ONLY консуматор,
БЕЗ нови fetch-ове (мандат 2.3). Цената влиза ВЕДНЪЖ (§R.3 — без втори percentile).

None ≠ 0: липсва цена/shares/TTM → тикерът се пропуска за тази дата (видимо в
n_tickers). ONTO няма ценови файл; GOOGL/META/DELL/PLTR/AI нямат dei shares →
извън медианата. Ретроспективна/descriptive.
"""

import bisect
import csv
import glob
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts_store as fs  # noqa: E402
from series_util import expanding_robust_z  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "app" / "data" / "prices"
UNIVERSE = ROOT / "config" / "universe.csv"
OUT = ROOT / "app" / "data" / "v2" / "multiple_v2.json"

MIN_TICKERS = 8      # минимум компании за валидна кръстосана медиана
MIN_WEEKS = 52       # ~1г седмична база за робастния z (аналог на "кратка база")
WEEK_START = "2023-01-06"   # петък


def load_universe():
    with open(UNIVERSE, encoding="utf-8-sig") as fh:
        return [r["symbol"].strip() for r in csv.DictReader(fh)
                if str(r.get("enabled", "1")).strip() in ("1", "true", "True")]


def load_price_series(ticker):
    f = PRICES / f"{ticker}.json"
    if not f.exists():
        return None
    pts = json.loads(f.read_text(encoding="utf-8"))["prices"]
    dates = [p["date"] for p in pts]
    closes = [p["close"] for p in pts]
    return dates, closes


def price_asof(series, d):
    """Последна цена на/преди d (PIT). None ако няма."""
    if series is None:
        return None
    dates, closes = series
    i = bisect.bisect_right(dates, d) - 1
    return closes[i] if i >= 0 else None


def fridays(start: str, end: str):
    cur = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cur <= end_d:
        yield cur.isoformat()
        cur += timedelta(days=7)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    universe = load_universe()
    price = {t: load_price_series(t) for t in universe}
    # последна ценова дата
    last_price = max((price[t][0][-1] for t in universe if price[t]), default="2026-06-26")

    rows = []
    for d in fridays(WEEK_START, last_price):
        ps_vals = []
        for t in universe:
            pr = price_asof(price[t], d)
            sh = fs.get_asof(t, "shares", d)          # PIT
            ttm = fs.ttm_asof(t, "revenue", d)        # PIT идентичност
            if pr is None or sh is None or ttm is None:
                continue
            shares_val, ttm_val = sh["value"], ttm["value"]
            if shares_val <= 0 or ttm_val <= 0:
                continue
            ps_vals.append((pr * shares_val) / ttm_val)
        if len(ps_vals) >= MIN_TICKERS:
            ps_vals.sort()
            n = len(ps_vals)
            med = ps_vals[n // 2] if n % 2 else (ps_vals[n // 2 - 1] + ps_vals[n // 2]) / 2
            rows.append({"date": d, "n_tickers": len(ps_vals), "median_ps": round(med, 4)})
        else:
            rows.append({"date": d, "n_tickers": len(ps_vals), "median_ps": None})

    zs = expanding_robust_z([r["median_ps"] for r in rows], min_history=MIN_WEEKS)
    for r, z in zip(rows, zs):
        r["z"] = round(z, 4) if z is not None else None

    out = {
        "series_type": "retrospective/descriptive",
        "voice": "trailing_multiple",
        "price_source": "app/data/prices/{TICKER}.json (v1, READ-ONLY, no new fetch)",
        "method": ("weekly (Fri) trailing P/S = (price[PIT] * shares[PIT]) / TTM_revenue"
                   "[PIT identity] per ticker -> universe median (>=8 tickers) -> "
                   "expanding robust z (median/MAD, min 52 weeks)"),
        "min_tickers": MIN_TICKERS, "min_history_weeks": MIN_WEEKS,
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    nonnull = [r for r in rows if r["median_ps"] is not None]
    zdef = [r for r in rows if r["z"] is not None]
    print("=== multiple_v2 (voice 3) ===")
    print(f"weeks: {len(rows)} | median_ps defined: {len(nonnull)} | z defined: {len(zdef)}")
    print("last 8 weekly points:")
    print(f"{'date':12} {'n_tick':>6} {'median_ps':>10} {'z':>8}")
    for r in rows[-8:]:
        z = "None" if r["z"] is None else f"{r['z']:.3f}"
        ps = "None" if r["median_ps"] is None else f"{r['median_ps']:.3f}"
        print(f"{r['date']:12} {r['n_tickers']:>6} {ps:>10} {z:>8}")


if __name__ == "__main__":
    main()
