# Falsifier report (F1-F3) — retrospective

Constants: config/v2/zones_signoff.json. Series: app/data/v2/gap_series.json +
zones_retro.json. Descriptive/retrospective; verdicts logged at each phase gate.

## F1 — "Каишката, която никога не се прибира"
Episode = first entry into an extreme zone; within 26 weeks the raw E-F spread
must narrow by >= 0.5 sigma; quota >= 2/3; verdict needs >= 3 episodes.
- sigma(G_raw) = 0.3244
- episodes (1): [{"date": "2024-11-15", "zone": "extreme_high", "G_raw0": 1.242, "narrowed_0.5sigma_within_26w": true}]
- narrowed: 1/1
- **Verdict: INSUFFICIENT DATA (1 episode(s) < 3)**

## F2 — "Преоблеченият ценови percentile" (cov-share, Appendix A)
Gate (Appendix A, Phase 3): price component cov-share in **var(G)** <= 0.6
AND |corr(G_z, multiple_z)| <= 0.9.
- **price cov-share in var(G) = 0.0074** (n=84 weeks) <- the gate
- (reference) multiple cov-share in var(E) = 0.7479
- corr(G_z, multiple_z) = 0.0081 (n=84 weeks)
- Note: F (revenue-growth + margin) co-moves with the multiple, so E-F cancels most
  of the price variance -> the GAP is not a disguised price percentile even though E
  is multiple-heavy (74.8% in var(E)).
- **Verdict: PASS (not falsified)**

## F3 — "Шум между отчетите"
Share of var(dG) in weeks WITHOUT an F-update <= 0.9.
- share = 0.2113 (dG n=83, no-F-update weeks=77)
- **Verdict: PASS (not falsified)**

## Summary
| Falsifier | Verdict |
|---|---|
| F1 | INSUFFICIENT DATA (1 episode(s) < 3) |
| F2 | PASS (not falsified) |
| F3 | PASS (not falsified) |
