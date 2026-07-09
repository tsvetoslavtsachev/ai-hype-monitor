"""
euphoria.py — Е-крак композит: E(t) (Фаза 2, 2.5).
==================================================
E(t) = средно на НАЛИЧНИТЕ компонентни z-та (седмичен каданс). Реторика и P&D
стъпват при filing (тримесечно, с ~45-дневен lag до наличност), froth тримесечно,
multiple седмично. Ако <2 налични компонента за дата → E=None (никакъв тих 0).
Пълна компонентна разбивка per дата. Изход: app/data/v2/euphoria_series.json.
Ретроспективна/descriptive.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from series_util import quarter_end_date  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "app" / "data" / "v2"
OUT = V2 / "euphoria_series.json"

FILING_LAG_DAYS = 45   # приблизителна забава до наличност на тримесечните гласове


def _load(name):
    p = V2 / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _quarterly_effective(series_obj, has_quarter_end=True):
    """[(effective_date, z)] сортирано — z става ефективно ~45 дни след края на трим."""
    out = []
    for r in series_obj["series"]:
        if r.get("z") is None:
            continue
        qe = r["quarter_end"] if has_quarter_end else quarter_end_date(r["quarter"])
        eff = (date.fromisoformat(qe) + timedelta(days=FILING_LAG_DAYS)).isoformat()
        out.append((eff, r["z"]))
    out.sort()
    return out


def _held(eff_list, d):
    """Последното z с effective_date ≤ d (held)."""
    val = None
    for eff, z in eff_list:
        if eff <= d:
            val = z
        else:
            break
    return val


def main():
    rhet = _load("rhetoric_series.json")
    pd_ = _load("promise_delivery.json")
    froth = _load("froth.json")
    mult = _load("multiple_v2.json")
    missing = [n for n, o in [("rhetoric", rhet), ("promise_delivery", pd_),
                              ("froth", froth), ("multiple", mult)] if o is None]
    if missing:
        print(f"[STOP] липсват компонентни серии: {missing}")
        sys.exit(1)

    rhet_eff = _quarterly_effective(rhet)
    pd_eff = _quarterly_effective(pd_)
    froth_eff = _quarterly_effective(froth, has_quarter_end=False)
    # multiple: седмична решетка (нейните дати са гръбнакът)
    mult_by_date = {r["date"]: r["z"] for r in mult["series"]}

    rows = []
    for r in mult["series"]:
        d = r["date"]
        comps = {
            "z_rhetoric": _held(rhet_eff, d),
            "z_promise_delivery": _held(pd_eff, d),
            "z_froth": _held(froth_eff, d),
            "z_multiple": mult_by_date.get(d),
        }
        avail = [v for v in comps.values() if v is not None]
        E = round(sum(avail) / len(avail), 4) if len(avail) >= 2 else None
        rows.append({"date": d, **{k: (round(v, 4) if v is not None else None)
                                   for k, v in comps.items()},
                     "n_components": len(avail), "E": E})

    out = {
        "series_type": "retrospective/descriptive",
        "composite": "euphoria E(t)",
        "method": ("weekly grid (multiple's Fridays); E = mean of available component z's "
                   "(rhetoric/P&D/froth held from ~45d after quarter-end = filing lag; "
                   "multiple weekly); E=None if <2 components available"),
        "filing_lag_days": FILING_LAG_DAYS,
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    defined = [r for r in rows if r["E"] is not None]
    print("=== euphoria E(t) (composite) ===")
    print(f"weeks: {len(rows)} | E defined: {len(defined)}")
    print(f"{'date':12} {'rhet':>7} {'p/d':>7} {'froth':>7} {'mult':>7} {'nC':>3} {'E':>8}")
    for r in rows[-8:]:
        def f(x):
            return "None" if x is None else f"{x:.2f}"
        print(f"{r['date']:12} {f(r['z_rhetoric']):>7} {f(r['z_promise_delivery']):>7} "
              f"{f(r['z_froth']):>7} {f(r['z_multiple']):>7} {r['n_components']:>3} {f(r['E']):>8}")


if __name__ == "__main__":
    main()
