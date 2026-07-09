"""
zones.py — зонова state machine (Фаза 3, 3.2).
==============================================
Прилага зоновия речник върху G_z: ladder ±a/±b, хистерезис (посочна лента),
dwell (потвърждение), stale→Неопределена. Скоростта dG₄ е САМО флаг (никога не
мести зоната). Всички константи от config/v2/zones_signoff.json.

Изходи:
- app/data/v2/zones_retro.json — РЕТРО зонова серия (instant + committed зона,
  velocity flag, преходи), етикет retrospective.
- app/data/v2/zone_journal.json — ЖИВ журнал, стартира от датата на фазата
  (append-only; ретро-преходите НЕ влизат тук — те са в zones_retro).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
SIGNOFF = ROOT / "config" / "v2" / "zones_signoff.json"
GAP = ROOT / "app" / "data" / "v2" / "gap_series.json"
OUT_RETRO = ROOT / "app" / "data" / "v2" / "zones_retro.json"
OUT_JOURNAL = ROOT / "app" / "data" / "v2" / "zone_journal.json"

PHASE_DATE = "2026-07-10"   # датата на Фаза 3 (живият журнал стартира оттук)

# индекси 0..4: extreme_low, mild_low, neutral, mild_high, extreme_high
ZKEYS = ["extreme_low", "mild_low", "neutral", "mild_high", "extreme_high"]


def _bounds(a, b):
    # долна/горна граница на всяка зона (idx 0..4)
    lower = [float("-inf"), -b, -a, a, b]
    upper = [-b, -a, a, b, float("inf")]
    return lower, upper


def nominal(gz, a, b):
    if gz >= b:
        return 4
    if gz >= a:
        return 3
    if gz > -a:
        return 2
    if gz > -b:
        return 1
    return 0


def target_zone(gz, cur, a, b, hyst):
    """Посочен хистерезис: за да напусне current, gz да прекоси границата с ≥hyst."""
    lower, upper = _bounds(a, b)
    nom = nominal(gz, a, b)
    if nom == cur:
        return cur
    if nom > cur:                              # нагоре
        return nom if gz >= upper[cur] + hyst else cur
    return nom if gz <= lower[cur] - hyst else cur    # надолу


def main():
    cfg = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    z = cfg["zones"]
    a, b = z["ladder"]["a"], z["ladder"]["b"]
    hyst = z["hysteresis"]
    dwell = z["dwell_weeks"]
    stale_max = z["stale_weeks_to_undefined"]
    names = z["names"]
    vel = cfg["velocity"]
    vflag = vel["flag_threshold_z"]
    vwin = vel["window_weeks"]

    gap = json.loads(GAP.read_text(encoding="utf-8"))["series"]

    committed = None          # индекс или "undefined" или None (преди първи данни)
    pending, pending_n = None, 0
    stale = 0
    series, transitions = [], []

    for i, r in enumerate(gap):
        gz, dg4 = r["G_z"], r["dG4"]
        date = r["date"]
        vel_flag = (dg4 is not None and abs(dg4) >= vflag)
        instant = None

        if gz is None:
            stale += 1
            if committed not in (None, "undefined") and stale >= stale_max:
                transitions.append({"date": date, "old": ZKEYS[committed] if isinstance(committed, int) else committed,
                                    "new": "undefined", "reason": f"stale {stale} weeks (no G_z)",
                                    "G_z": None})
                committed = "undefined"
                pending, pending_n = None, 0
        else:
            stale = 0
            instant = nominal(gz, a, b)
            if committed is None or committed == "undefined":
                # (ре)инициализация без хистерезис
                old = committed
                committed = instant
                pending, pending_n = None, 0
                transitions.append({"date": date, "old": old if old else "init",
                                    "new": ZKEYS[committed], "reason": "init/resume",
                                    "G_z": gz, "dG4": dg4})
            else:
                tgt = target_zone(gz, committed, a, b, hyst)
                if tgt == committed:
                    pending, pending_n = None, 0
                else:
                    if pending == tgt:
                        pending_n += 1
                    else:
                        pending, pending_n = tgt, 1
                    if pending_n >= dwell:
                        # кой движи: E vs F промяна над скоростния прозорец
                        drv = None
                        if i >= vwin:
                            dE = (r["E"] - gap[i - vwin]["E"]) if (r["E"] is not None and gap[i - vwin]["E"] is not None) else None
                            dF = (r["F"] - gap[i - vwin]["F"]) if (r["F"] is not None and gap[i - vwin]["F"] is not None) else None
                            if dE is not None and dF is not None:
                                drv = {"driver": "E" if abs(dE) >= abs(dF) else "F",
                                       "dE": round(dE, 4), "dF": round(dF, 4)}
                        transitions.append({"date": date, "old": ZKEYS[committed],
                                            "new": ZKEYS[tgt], "G_z": gz, "dG4": dg4,
                                            "velocity_flag": vel_flag, "driving": drv})
                        committed = tgt
                        pending, pending_n = None, 0

        series.append({"date": date, "G_z": gz, "dG4": dg4,
                       "instant_zone": (ZKEYS[instant] if instant is not None else None),
                       "committed_zone": (ZKEYS[committed] if isinstance(committed, int) else committed),
                       "velocity_flag": vel_flag})

    # occupancy (committed) — за сравнение със симулацията
    from collections import Counter
    occ = Counter(s["committed_zone"] for s in series if s["committed_zone"] is not None)
    tot = sum(occ.values())
    occ_pct = {k: round(100 * v / tot, 1) for k, v in occ.items()} if tot else {}

    retro = {
        "series_type": "retrospective/descriptive",
        "constants_source": "config/v2/zones_signoff.json",
        "zone_names": names,
        "occupancy_pct": occ_pct,
        "n_transitions": len(transitions),
        "transitions": transitions,
        "series": series,
    }
    OUT_RETRO.write_text(json.dumps(retro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── ЖИВ журнал: стартира от датата на фазата (baseline = последна ретро зона) ──
    baseline = next((s for s in reversed(series) if s["committed_zone"] not in (None, "undefined")), None)
    journal = {
        "type": "LIVE zone journal (append-only)",
        "live_start_date": PHASE_DATE,
        "note": "Ретро-преходите са в zones_retro.json (descriptive). Тук се пишат САМО живи преходи от датата на фазата нататък.",
        "baseline": ({"as_of_data": baseline["date"], "zone": baseline["committed_zone"],
                      "G_z": baseline["G_z"]} if baseline else None),
        "entries": [],
    }
    OUT_JOURNAL.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== zones.py ===")
    print(f"weeks: {len(series)} | committed occupancy: {occ_pct}")
    print(f"transitions: {len(transitions)}")
    for t in transitions:
        print(f"  {t['date']}  {t.get('old')} -> {t['new']}  G_z={t.get('G_z')}  {t.get('reason','')}")
    print(f"LIVE journal baseline: {journal['baseline']}")


if __name__ == "__main__":
    main()
