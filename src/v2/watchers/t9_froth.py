"""
t9_froth.py — watcher за T9 (froth tripwire), Фаза 4 (4.2).
==========================================================
Праговете от config/v2/zones_signoff.json.tripwire_T9 срещу app/data/v2/froth.json.
T9a: AI-дял >= 0.65 · T9b: не-tech дял >= 0.85. Rearm: AI-дял < 0.50 две поредни
тримесечия. Пише КАНДИДАТ в out/watcher_t9.md — човек потвърждава; НИКАКВО
автоматично сменяне на статуса в tripwires.yaml.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SIGNOFF = ROOT / "config" / "v2" / "zones_signoff.json"
FROTH = ROOT / "app" / "data" / "v2" / "froth.json"
OUT = ROOT / "out" / "watcher_t9.md"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(SIGNOFF.read_text(encoding="utf-8"))["tripwire_T9"]
    t9a, t9b = cfg["T9a_ai_share_threshold"], cfg["T9b_nontech_share_threshold"]
    froth = json.loads(FROTH.read_text(encoding="utf-8"))
    series = froth["series"]
    latest = series[-1]
    ai_share = latest["share"]                    # 0..1
    split = froth.get("latest_quarter_sic_split", {})
    nontech = (split.get("nontech_share_pct") or 0) / 100.0

    t9a_hit = ai_share is not None and ai_share >= t9a
    t9b_hit = nontech >= t9b
    candidate = t9a_hit or t9b_hit
    # rearm: AI-дял < 0.50 две поредни тримесечия
    last2 = [s["share"] for s in series[-2:] if s["share"] is not None]
    rearm = len(last2) == 2 and all(s < 0.50 for s in last2)

    lines = [
        "# Watcher T9 (froth) — CANDIDATE (human confirms; no auto-status)",
        "",
        f"- Latest quarter: **{latest['quarter']}**",
        f"- T9a AI-share: **{ai_share:.3f}** vs threshold {t9a}  -> {'HIT' if t9a_hit else 'no'}",
        f"- T9b non-tech share: **{nontech:.3f}** vs threshold {t9b}  -> {'HIT' if t9b_hit else 'no'}",
        f"- **CANDIDATE: {'FIRE T9' if candidate else 'not fired'}**",
        f"- rearm (AI-share < 0.50 x2 quarters): {rearm}",
        "",
        f"provenance: froth.json ({latest['quarter']}, ai_hits={latest['ai_hits']}/"
        f"{latest['s1_root_filings']}); thresholds config/v2/zones_signoff.json.tripwire_T9",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[t9_froth] {latest['quarter']}: AI={ai_share:.3f}(>={t9a}? {t9a_hit}) "
          f"nontech={nontech:.3f}(>={t9b}? {t9b_hit}) -> candidate={candidate} -> {OUT.name}")
    return candidate


if __name__ == "__main__":
    main()
