"""
gap.py — G ядрото (Фаза 3, 3.1).
================================
G(t) = E_z(t) − F_z(t), после G_z = робастен z спрямо РЕТРОСПЕКТИВНАТА G серия
(signoff z_scale_base) + скорост dG₄ (4-седмичен наклон на G_z).

F-крак (състав пре-регистриран, user-confirmed): равни тегла на 2 компонента —
приходен ръст YoY и оперативен марж, всеки TTM/PIT през facts_store. Агрегация
(signoff): per компания → МЕДИАНА в слоя → layer_weights (ре-нормализирани над
наличните слоеве) → универсална стойност → робастен z (ретро/descriptive).
F(t)=средно на наличните компонентни z (min 2 = двата). cap-weighting ЗАБРАНЕН.

ВСИЧКИ константи от config/v2/zones_signoff.json — нула на ръка. None ≠ 0.
Ретроспективна/descriptive серия.
"""

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts_store as fs  # noqa: E402
from series_util import (  # noqa: E402
    robust_z, calendar_quarter, quarter_end_date, quarter_sort_key,
    quarters_between, _median,
)

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "config" / "universe.csv"
SIGNOFF = ROOT / "config" / "v2" / "zones_signoff.json"
EUPHORIA = ROOT / "app" / "data" / "v2" / "euphoria_series.json"
OUT = ROOT / "app" / "data" / "v2" / "gap_series.json"

FILING_LAG_DAYS = 45   # каданс с E-крака (тримесечните гласове стъпват при filing)


def load_layers():
    out = {}
    with open(UNIVERSE, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("enabled", "1")).strip() in ("1", "true", "True"):
                out[r["symbol"].strip()] = r["layer"].strip()
    return out


def _as_of(q):
    return (date.fromisoformat(quarter_end_date(q)) + timedelta(days=FILING_LAG_DAYS)).isoformat()


def _year_before(iso):
    d = date.fromisoformat(iso)
    return d.replace(year=d.year - 1).isoformat()


def rev_growth_yoy(ticker, as_of):
    now = fs.ttm_asof(ticker, "revenue", as_of)
    yr = fs.ttm_asof(ticker, "revenue", _year_before(as_of))
    if not now or not yr or yr["value"] <= 0:
        return None
    return (now["value"] - yr["value"]) / yr["value"]


def operating_margin(ticker, as_of):
    rev = fs.ttm_asof(ticker, "revenue", as_of)
    op = fs.ttm_asof(ticker, "operating_income", as_of)
    if not rev or not op or rev["value"] <= 0:
        return None
    return op["value"] / rev["value"]


COMPONENT_FN = {"revenue_growth_yoy": rev_growth_yoy, "operating_margin": operating_margin}


def universe_value(fn, as_of, layers, layer_weights):
    """per компания -> медиана в слоя -> layer_weights (ре-норм над наличните)."""
    by_layer = {}
    for t, lyr in layers.items():
        v = fn(t, as_of)
        if v is not None:
            by_layer.setdefault(lyr, []).append(v)
    layer_med = {lyr: _median(vs) for lyr, vs in by_layer.items()}
    avail_w = {lyr: layer_weights[lyr] for lyr in layer_med if lyr in layer_weights}
    tot = sum(avail_w.values())
    if tot == 0:
        return None
    return sum(layer_med[lyr] * (w / tot) for lyr, w in avail_w.items())


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    layer_weights = cfg["weights"]["layer_weights"]
    components = cfg["f_leg_composition"]["components"]
    min_f = cfg["weights"]["min_components_F"]
    vel_win = cfg["velocity"]["window_weeks"]
    layers = load_layers()

    # ── F-крак: тримесечни компонентни серии ─────────────────────────────
    euph = json.loads(EUPHORIA.read_text(encoding="utf-8"))["series"]
    q_hi = calendar_quarter(euph[-1]["date"])
    quarters = quarters_between("2022Q4", q_hi)

    raw_comp = {c: [] for c in components}      # универсална стойност per трим.
    for q in quarters:
        aof = _as_of(q)
        for c in components:
            raw_comp[c].append(universe_value(COMPONENT_FN[c], aof, layers, layer_weights))

    # робастен z (descriptive: спрямо цялата ретро серия на компонента)
    z_comp = {}
    for c in components:
        series = raw_comp[c]
        z_comp[c] = [robust_z(x, [v for v in series if v is not None]) if x is not None else None
                     for x in series]

    F_q = []
    for i, q in enumerate(quarters):
        zs = [z_comp[c][i] for c in components if z_comp[c][i] is not None]
        Fv = round(sum(zs) / len(zs), 4) if len(zs) >= min_f else None
        F_q.append({"quarter": q, "quarter_end": quarter_end_date(q), "effective": _as_of(q),
                    **{f"z_{c}": (round(z_comp[c][i], 4) if z_comp[c][i] is not None else None)
                       for c in components},
                    **{f"raw_{c}": (round(raw_comp[c][i], 6) if raw_comp[c][i] is not None else None)
                       for c in components},
                    "F": Fv})

    # ── G: седмична решетка (E − F held), после G_z спрямо ретро ──────────
    f_eff = sorted([(r["effective"], r["F"]) for r in F_q if r["F"] is not None])

    def held_F(d):
        val = None
        for eff, fv in f_eff:
            if eff <= d:
                val = fv
            else:
                break
        return val

    rows = []
    for r in euph:
        d, E = r["date"], r["E"]
        F = held_F(d)
        g_raw = round(E - F, 4) if (E is not None and F is not None) else None
        rows.append({"date": d, "E": E, "F": F, "G_raw": g_raw})

    # G_z = робастен z спрямо ретроспективната G_raw серия (signoff z_scale_base)
    base = [r["G_raw"] for r in rows if r["G_raw"] is not None]
    for r in rows:
        z = robust_z(r["G_raw"], base) if r["G_raw"] is not None else None
        r["G_z"] = round(z, 4) if z is not None else None

    # скорост dG₄ = G_z(t) − G_z(t−4 седмици)
    for i, r in enumerate(rows):
        prev = rows[i - vel_win]["G_z"] if i >= vel_win else None
        r["dG4"] = round(r["G_z"] - prev, 4) if (r["G_z"] is not None and prev is not None) else None

    out = {
        "series_type": "retrospective/descriptive",
        "core": "G(t) = E_z - F_z",
        "constants_source": "config/v2/zones_signoff.json",
        "f_leg": {"components": components, "aggregation": "median_within_layer -> layer_weights (renorm) -> robust z (retro)"},
        "method": ("F quarterly (TTM/PIT, filing-lag 45d, held weekly); G_raw = E - F; "
                   "G_z = robust z of G_raw over retrospective series; dG4 = 4-week slope of G_z"),
        "f_quarterly": F_q,
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fdef = [r for r in F_q if r["F"] is not None]
    gdef = [r for r in rows if r["G_z"] is not None]
    print("=== gap.py (G core) ===")
    print(f"F quarters defined: {len(fdef)}/{len(F_q)} | G_z weeks defined: {len(gdef)}/{len(rows)}")
    print("F-leg last 6 quarters:")
    print(f"{'quarter':8} {'z_revg':>8} {'z_opm':>8} {'F':>8}")
    for r in F_q[-6:]:
        def f(x):
            return "None" if x is None else f"{x:.3f}"
        print(f"{r['quarter']:8} {f(r.get('z_revenue_growth_yoy')):>8} "
              f"{f(r.get('z_operating_margin')):>8} {f(r['F']):>8}")
    print("G last 6 weeks:")
    print(f"{'date':12} {'E':>7} {'F':>7} {'G_raw':>7} {'G_z':>7} {'dG4':>7}")
    for r in rows[-6:]:
        def f(x):
            return "None" if x is None else f"{x:.2f}"
        print(f"{r['date']:12} {f(r['E']):>7} {f(r['F']):>7} {f(r['G_raw']):>7} "
              f"{f(r['G_z']):>7} {f(r['dG4']):>7}")


if __name__ == "__main__":
    main()
