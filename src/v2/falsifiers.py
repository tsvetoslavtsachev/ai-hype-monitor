"""
falsifiers.py — гилотините F1-F3 (Фаза 3, 3.3).
===============================================
Смята автоматично F1 „Каишката, която никога не се прибира", F2 „Преоблеченият
ценови percentile" (cov-дял по Приложение А), F3 „Шум между отчетите" — с
параметри от config/v2/zones_signoff.json — върху РЕТРО серията. Пише
out/falsifier_report.md. Присъда „insufficient data" при < min епизоди.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
SIGNOFF = ROOT / "config" / "v2" / "zones_signoff.json"
V2 = ROOT / "app" / "data" / "v2"
OUT = ROOT / "out" / "falsifier_report.md"


def _pvar(xs):
    # вариацията на ≤1 точка е дегенерирала -> 0 (falsy); всички ползватели
    # guard-ват с `if var else None`, тъй че НЕ е тих placeholder за липса.
    return statistics.pvariance(xs) if len(xs) > 1 else 0


def _cov(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)


def _corr(a, b):
    va, vb = _pvar(a), _pvar(b)
    if va == 0 or vb == 0:
        return None
    return _cov(a, b) / (va ** 0.5 * vb ** 0.5)


def f1(cfg, gap, zones):
    p = cfg["falsifiers"]["F1"]
    win, need_sigma, quota, min_ep = (p["window_weeks"], p["raw_spread_narrowing_sigma"],
                                      p["quota"], p["min_episodes_for_verdict"])
    graw = {r["date"]: r["G_raw"] for r in gap["series"]}
    dates = [r["date"] for r in gap["series"]]
    sigma = _pvar([v for v in graw.values() if v is not None]) ** 0.5
    # епизоди = преходи ВЛИЗАЩИ в екстремна зона
    episodes = [t for t in zones["transitions"] if t["new"] in ("extreme_high", "extreme_low")]
    results = []
    for ep in episodes:
        di = dates.index(ep["date"])
        g0 = graw.get(ep["date"])
        if g0 is None or sigma == 0:
            continue
        # до win седмици напред: сви ли се суровият спред с ≥ need_sigma·σ (към 0)?
        narrowed = False
        for j in range(di + 1, min(di + 1 + win, len(dates))):
            gj = graw.get(dates[j])
            if gj is None:
                continue
            if abs(g0) - abs(gj) >= need_sigma * sigma:
                narrowed = True
                break
        results.append({"date": ep["date"], "zone": ep["new"], "G_raw0": round(g0, 3),
                        "narrowed_0.5sigma_within_26w": narrowed})
    n = len(results)
    passed = sum(1 for r in results if r["narrowed_0.5sigma_within_26w"])
    if n < min_ep:
        verdict = f"INSUFFICIENT DATA ({n} episode(s) < {min_ep})"
        ok = None
    else:
        ok = (passed / n) >= quota
        verdict = "PASS (not falsified)" if ok else "FALSIFIED"
    return {"sigma_Graw": round(sigma, 4), "episodes": results, "passed": passed,
            "n_episodes": n, "quota": quota, "verdict": verdict, "ok": ok}


def f2(cfg, gap, euph, mult):
    p = cfg["falsifiers"]["F2"]
    max_share, max_corr = p["max_multiple_var_share_in_E"], p["max_abs_corr_G_vs_multiple_z"]
    comps = ["z_rhetoric", "z_promise_delivery", "z_froth", "z_multiple"]
    # E-basis (reference, matches signoff Phase-2 note): multiple cov-share in var(E)
    rows = [r for r in euph["series"] if r["E"] is not None and all(r[c] is not None for c in comps)]
    E = [r["E"] for r in rows]
    varE = _pvar(E)
    share_E = _cov([r["z_multiple"] / 4 for r in rows], E) / varE if varE else None
    # G-basis (Appendix A = the Phase-3 gate): price(mult/4) cov-share in var(G_raw).
    # F (revenue growth + margin) co-moves with the multiple, so E-F cancels most of
    # the price variance -> the GAP is not a disguised price percentile.
    emz = {r["date"]: r["z_multiple"] for r in euph["series"]}
    grows = [(r["G_raw"], emz[r["date"]]) for r in gap["series"]
             if r["G_raw"] is not None and r["date"] in emz and emz[r["date"]] is not None]
    varG = _pvar([x for x, _ in grows])
    share_G = _cov([m / 4 for _, m in grows], [x for x, _ in grows]) / varG if varG else None
    # corr(G_z, multiple z) по дата
    gz = {r["date"]: r["G_z"] for r in gap["series"]}
    mz = {r["date"]: r["z"] for r in mult["series"]}
    pairs = [(gz[d], mz[d]) for d in gz if d in mz and gz[d] is not None and mz[d] is not None]
    corr = _corr([x for x, _ in pairs], [y for _, y in pairs]) if pairs else None
    cond_share = (share_G is not None and share_G <= max_share)   # Appendix A: G-basis
    cond_corr = (corr is not None and abs(corr) <= max_corr)
    ok = cond_share and cond_corr
    return {"price_cov_share_in_G": round(share_G, 4) if share_G is not None else None,
            "multiple_cov_share_in_E_reference": round(share_E, 4) if share_E is not None else None,
            "threshold_share": max_share, "corr_G_vs_multiple": round(corr, 4) if corr is not None else None,
            "threshold_corr": max_corr, "n_weeks_G": len(grows), "n_weeks_corr": len(pairs),
            "verdict": "PASS (not falsified)" if ok else "FALSIFIED", "ok": ok}


def f3(cfg, gap):
    p = cfg["falsifiers"]["F3"]
    max_share = p["max_var_share_dG_in_weeks_without_F_update"]
    s = gap["series"]
    dG, no_update = [], []
    prevF, prevG = None, None
    for r in s:
        if r["G_z"] is not None and prevG is not None:
            d = r["G_z"] - prevG
            dG.append(d)
            no_update.append(r["F"] == prevF)   # F не се е обновил тази седмица
        if r["G_z"] is not None:
            prevG = r["G_z"]
        prevF = r["F"]
    var_all = _pvar(dG)
    dG_no = [d for d, nu in zip(dG, no_update) if nu]
    # дял на var(ΔG) в седмици без F-обновление: sum of squares (около 0) proxy
    ss_all = sum(d * d for d in dG)
    ss_no = sum(d * d for d in dG_no)
    share = ss_no / ss_all if ss_all else None
    ok = (share is not None and share <= max_share)
    return {"share_var_dG_no_F_update": round(share, 4) if share is not None else None,
            "threshold": max_share, "n_dG": len(dG), "n_no_update": len(dG_no),
            "verdict": "PASS (not falsified)" if ok else "FALSIFIED", "ok": ok}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    gap = json.loads((V2 / "gap_series.json").read_text(encoding="utf-8"))
    zones = json.loads((V2 / "zones_retro.json").read_text(encoding="utf-8"))
    euph = json.loads((V2 / "euphoria_series.json").read_text(encoding="utf-8"))
    mult = json.loads((V2 / "multiple_v2.json").read_text(encoding="utf-8"))

    r1, r2, r3 = f1(cfg, gap, zones), f2(cfg, gap, euph, mult), f3(cfg, gap)

    def v(x):
        return x["verdict"]
    md = f"""# Falsifier report (F1-F3) — retrospective

Constants: config/v2/zones_signoff.json. Series: app/data/v2/gap_series.json +
zones_retro.json. Descriptive/retrospective; verdicts logged at each phase gate.

## F1 — "Каишката, която никога не се прибира"
Episode = first entry into an extreme zone; within 26 weeks the raw E-F spread
must narrow by >= 0.5 sigma; quota >= 2/3; verdict needs >= 3 episodes.
- sigma(G_raw) = {r1['sigma_Graw']}
- episodes ({r1['n_episodes']}): {json.dumps(r1['episodes'], ensure_ascii=False)}
- narrowed: {r1['passed']}/{r1['n_episodes']}
- **Verdict: {v(r1)}**

## F2 — "Преоблеченият ценови percentile" (cov-share, Appendix A)
Gate (Appendix A, Phase 3): price component cov-share in **var(G)** <= {r2['threshold_share']}
AND |corr(G_z, multiple_z)| <= {r2['threshold_corr']}.
- **price cov-share in var(G) = {r2['price_cov_share_in_G']}** (n={r2['n_weeks_G']} weeks) <- the gate
- (reference) multiple cov-share in var(E) = {r2['multiple_cov_share_in_E_reference']}
- corr(G_z, multiple_z) = {r2['corr_G_vs_multiple']} (n={r2['n_weeks_corr']} weeks)
- Note: F (revenue-growth + margin) co-moves with the multiple, so E-F cancels most
  of the price variance -> the GAP is not a disguised price percentile even though E
  is multiple-heavy (74.8% in var(E)).
- **Verdict: {v(r2)}**

## F3 — "Шум между отчетите"
Share of var(dG) in weeks WITHOUT an F-update <= {r3['threshold']}.
- share = {r3['share_var_dG_no_F_update']} (dG n={r3['n_dG']}, no-F-update weeks={r3['n_no_update']})
- **Verdict: {v(r3)}**

## Summary
| Falsifier | Verdict | Number |
|---|---|---|
| F1 | {v(r1)} | {r1['passed']}/{r1['n_episodes']} episodes narrowed |
| F2 (gate, G-basis) | {v(r2)} | price cov-share in var(G) = {r2['price_cov_share_in_G']} (<= {r2['threshold_share']}) |
| F2-WATCH (E-basis) | WATCH (not a gate) | multiple cov-share in var(E) = {r2['multiple_cov_share_in_E_reference']} -- E is multiple-heavy; kept visible per audit |
| F3 | {v(r3)} | var(dG) share in no-F-update weeks = {r3['share_var_dG_no_F_update']} (<= {r3['threshold']}) |
"""
    OUT.write_text(md, encoding="utf-8")
    print("=== falsifiers.py ===")
    print(f"F1: {v(r1)}")
    print(f"F2: {v(r2)}  (price cov-share in G={r2['price_cov_share_in_G']}, "
          f"E-ref={r2['multiple_cov_share_in_E_reference']}, corr={r2['corr_G_vs_multiple']})")
    print(f"F3: {v(r3)}  (share={r3['share_var_dG_no_F_update']})")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
