"""
onepager.py — седмичен едностраничник (Фаза 4, 4.3).
====================================================
Генерира out/weekly/YYYY-MM-DD.md: G ниво + скорост + зона, компонентна разбивка
(E: 4 гласа · F: 2 фундамента), случени tripwire-ове от последните 14 дни, и
PROVENANCE таблица (всяко число -> съхранен вход + known_at). БЕЗ прилагателни без
числова основа. Шаблонът е в кода (не в LLM). Детерминистичен (as_of подаван).
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "app" / "data" / "v2"
OUTDIR = ROOT / "out" / "weekly"

AS_OF = "2026-07-10"       # датата на фазата (жив едностраничник); подавай за друга


def _last_defined(series, key):
    for r in reversed(series):
        if r.get(key) is not None:
            return r
    return None


def main(as_of=AS_OF):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    gap = json.loads((V2 / "gap_series.json").read_text(encoding="utf-8"))
    zones = json.loads((V2 / "zones_retro.json").read_text(encoding="utf-8"))
    euph = json.loads((V2 / "euphoria_series.json").read_text(encoding="utf-8"))["series"]
    froth = json.loads((V2 / "froth.json").read_text(encoding="utf-8"))
    tw = yaml.safe_load((V2 / "tripwires.yaml").read_text(encoding="utf-8"))

    grow = _last_defined(gap["series"], "G_z")
    wk = grow["date"]
    zrow = next((s for s in zones["series"] if s["date"] == wk), {})
    erow = next((r for r in euph if r["date"] == wk), {})
    fq = _last_defined(gap["f_quarterly"], "F")
    froth_last = froth["series"][-1]

    zone = zrow.get("committed_zone")
    zone_bg = zones["zone_names"].get(zone, zone)

    # tripwire-ове, случени в последните 14 дни от as_of
    cutoff = (date.fromisoformat(as_of) - timedelta(days=14)).isoformat()
    fired_recent = [t for t in tw["tripwires"]
                    if t["status"] == "fired" and t["fired_date"] and t["fired_date"] >= cutoff]
    fired_all = [t for t in tw["tripwires"] if t["status"] == "fired"]

    # provenance записи (metric, value, source, known_at)
    prov = [
        ("G_z", grow["G_z"], "app/data/v2/gap_series.json:last(G_z)", wk),
        ("dG4", grow["dG4"], "app/data/v2/gap_series.json:last(dG4)", wk),
        ("G_raw", grow["G_raw"], "app/data/v2/gap_series.json:last(G_raw)", wk),
        ("zone", zone, "app/data/v2/zones_retro.json:committed_zone@" + wk, wk),
        ("velocity_flag", zrow.get("velocity_flag"), "app/data/v2/zones_retro.json:velocity_flag@" + wk, wk),
        ("z_rhetoric", erow.get("z_rhetoric"), "euphoria_series.json:z_rhetoric@" + wk, wk),
        ("z_promise_delivery", erow.get("z_promise_delivery"), "euphoria_series.json:z_promise_delivery@" + wk, wk),
        ("z_froth", erow.get("z_froth"), "euphoria_series.json:z_froth@" + wk, wk),
        ("z_multiple", erow.get("z_multiple"), "euphoria_series.json:z_multiple@" + wk, wk),
        ("E", erow.get("E"), "euphoria_series.json:E@" + wk, wk),
        ("F", fq["F"], "gap_series.json:f_quarterly:last(F)", fq["quarter"]),
        ("z_revenue_growth_yoy", fq.get("z_revenue_growth_yoy"), "gap_series.json:f_quarterly:last", fq["quarter"]),
        ("z_operating_margin", fq.get("z_operating_margin"), "gap_series.json:f_quarterly:last", fq["quarter"]),
        ("froth_share", froth_last["share"], "froth.json:last(share)", froth_last["quarter"]),
    ]

    def f(x):
        return "None" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))

    L = [f"# AI Hype Monitor v2 — седмичен едностраничник",
         f"**As of:** {as_of}  ·  **Данни до:** {wk} (последна пълна G седмица)",
         "",
         "## Разминаване G (еуфория − фундамент)",
         f"- **G_z = {f(grow['G_z'])}**  ·  скорост dG₄ = {f(grow['dG4'])}  "
         f"({'скоростен ФЛАГ' if zrow.get('velocity_flag') else 'без флаг'})",
         f"- **Зона: {zone_bg}**  (G_raw = {f(grow['G_raw'])} = E − F)",
         f"- Едно verified изречение: разминаването е G_z={f(grow['G_z'])} робастни σ спрямо "
         f"собствената си ретро история; зоната е {zone_bg}.",
         "",
         "## Компонентна разбивка",
         "**Еуфория E (4 гласа):**",
         f"- реторика z={f(erow.get('z_rhetoric'))} · обещание/доставка z={f(erow.get('z_promise_delivery'))} "
         f"· froth z={f(erow.get('z_froth'))} · множител z={f(erow.get('z_multiple'))} -> E={f(erow.get('E'))}",
         "**Фундамент F (2 крака, тримесечен):**",
         f"- приходен ръст z={f(fq.get('z_revenue_growth_yoy'))} · оперативен марж z={f(fq.get('z_operating_margin'))} "
         f"-> F={f(fq['F'])}  ({fq['quarter']})",
         "",
         "## Журнал на пукнатините (случени в последните 14 дни)"]
    if fired_recent:
        for t in fired_recent:
            L.append(f"- **{t['id']} {t['name']}** — {t['fired_date']} ({t['source']})")
            L.append(f"  - мечи: {t['bearish']} · бичи: {t['bullish']}")
    else:
        L.append("- (няма случени в последните 14 дни)")
    L.append(f"- Общо случени към момента: {len(fired_all)}/{len(tw['tripwires'])} "
             f"({', '.join(t['id'] for t in fired_all)})")
    L += ["", "## Provenance (всяко число -> съхранен вход)",
          "| metric | value | source | known_at |", "|---|---|---|---|"]
    for m, v, src, ka in prov:
        L.append(f"| {m} | {f(v)} | {src} | {ka} |")
    L += ["", "_Числата идват от детерминистичен код; froth от EDGAR FTS; F от SEC XBRL "
          "(PIT); цени от price-archive. Няма прилагателни без числова основа._"]

    out = OUTDIR / f"{as_of}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[onepager] as_of {as_of}, data through {wk}: G_z={f(grow['G_z'])}, zone={zone_bg}, "
          f"fired_recent={len(fired_recent)} -> {out.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    # По избор: as-of дата като аргумент (както render_onepager_html.py), иначе AS_OF.
    main(sys.argv[1] if len(sys.argv) > 1 else AS_OF)
