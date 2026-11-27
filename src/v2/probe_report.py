"""
probe_report.py: таблиците и мерките на двете проби (ПРОЛЕТР9, Фаза 3). Без мрежа.
==================================================================================
Мярката, приета от Ц. на 27.11.2026: серията „мърда“, ако сменя посоката си поне 2 пъти и размахът
(от дъното до върха) е поне 25% от медианата ѝ; „не повтаря цената“, ако корелацията на промените ѝ
с промените на пазарната стрелка е под 0,7 по абсолютна стойност. Думите: тримесечно (по
тримесечието на подаване). Wikipedia: по 4-седмични промени, без застъпване.

Плюс: стрелката на историята със и без съставката за последните 8 тримесечия (правилата на
strelki.py: индекс 100 в базата, геометрична средна, стойността важи от края + 45 дни).

Пуск: python src/v2/probe_report.py [--facts-dir ...]; пише app/data/v2/probes/probe_report.md.
"""

import argparse
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts_store as fs  # noqa: E402
import strelki as s  # noqa: E402

PROBES = s.V2 / "probes"
MIN_TURNS, MIN_RANGE, MAX_CORR = 2, 0.25, 0.7


def turns(vals):
    d = [b - a for a, b in zip(vals, vals[1:]) if b != a]
    return sum(1 for a, b in zip(d, d[1:]) if (a > 0) != (b > 0))


def rng(vals):
    return (max(vals) - min(vals)) / statistics.median(vals)


def corr(x, y):
    if len(x) < 3:
        return None
    mx, my = statistics.mean(x), statistics.mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else None


def verdict(vals, cx):
    t, r = turns(vals), rng(vals)
    moves = t >= MIN_TURNS and r >= MIN_RANGE
    own = cx is not None and abs(cx) < MAX_CORR
    return {"turns": t, "range_vs_median": round(r, 3), "corr_with_market": None if cx is None else round(cx, 3),
            "moves": moves, "not_price": own, "passes": moves and own}


def market_levels():
    mk = s.market_arrow(s.market_series())
    return {d: v[0] for d, v in mk.items()}


def at_or_before(levels, d):
    ks = [k for k in sorted(levels) if k <= d]
    return levels[ks[-1]] if ks else None


def pct(a, b):
    return (b / a - 1) * 100


def words_section(mlev, qvals):
    p = PROBES / "ai_words.json"
    if not p.exists():
        return ["## Думите в съобщенията за резултати", "", "Няма `app/data/v2/probes/ai_words.json`: пробата не е пусната.", ""], None
    w = json.loads(p.read_text(encoding="utf-8"))
    rows = [r for r in w["series"] if r["share"] is not None]
    qs = [r["filing_quarter"] for r in rows]
    sh = [r["share"] for r in rows]
    mq = [at_or_before(mlev, s.qend(q).isoformat()) for q in qs]
    pairs = [(pct(sh[i - 1], sh[i]), pct(mq[i - 1], mq[i])) for i in range(1, len(qs)) if mq[i - 1] and mq[i]]
    v = verdict(sh, corr([a for a, _ in pairs], [b for _, b in pairs]))
    L = ["## Думите в съобщенията за резултати (по тримесечието на подаване)", "",
         f"Числител `{w['method']['numerator']}`, знаменател `{w['method']['denominator']}`, 8-K; {w['source']}. "
         f"Пусната на {w['built']}.", "",
         "| тримесечие на подаване | с AI | всички | дял | промяна | пазарът в края | промяна на пазара |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows):
        ch = "" if i == 0 else f"{pct(sh[i - 1], sh[i]):+.1f}%"
        mch = "" if i == 0 or not mq[i - 1] or not mq[i] else f"{pct(mq[i - 1], mq[i]):+.1f}%"
        L.append(f"| {r['filing_quarter']} | {r['ai_docs']} | {r['earnings_like_docs']} | {r['share']:.4f} | {ch} | "
                 f"{'' if mq[i] is None else f'{mq[i]:.1f}'} | {mch} |")
    smp = w.get("sample_last_quarter", {})
    L += ["", f"Какво брои числителят ({smp.get('quarter')}, първите {smp.get('n')} документа): типове {smp.get('file_type')}; "
              f"точки на 8-K {smp.get('items')}.", "",
          f"Мерките: смени на посоката {v['turns']} (нужни поне {MIN_TURNS}); размах {v['range_vs_median']:.0%} от "
          f"медианата (нужни поне {MIN_RANGE:.0%}); корелация на тримесечните промени с пазарната стрелка "
          f"{v['corr_with_market']} (нужно под {MAX_CORR} по абсолютна стойност). "
          f"Мърда: {'да' if v['moves'] else 'не'}. Не повтаря цената: {'да' if v['not_price'] else 'не'}.", ""]
    for r in rows:
        if r["filing_quarter"] in qvals:
            qvals[r["filing_quarter"]]["words"] = r["share"]
    return L, v


def wiki_section(mlev, qvals):
    p = PROBES / "wiki.json"
    if not p.exists():
        return ["## Вниманието от Wikipedia", "", "Няма `app/data/v2/probes/wiki.json`: пробата не е пусната.", ""], None
    w = json.loads(p.read_text(encoding="utf-8"))
    rows = w["series"]
    step = rows[::-1][::4][::-1]                          # всеки 4-ти петък назад от последния, без застъпване
    tot = [r["total"] for r in step]
    mk = [at_or_before(mlev, r["week_end"]) for r in step]
    pairs = [(pct(tot[i - 1], tot[i]), pct(mk[i - 1], mk[i])) for i in range(1, len(step)) if mk[i - 1] and mk[i]]
    v = verdict(tot, corr([a for a, _ in pairs], [b for _, b in pairs]))
    L = ["## Вниманието от Wikipedia (седмици до петък, на 4 седмици)", "",
         f"Кошницата: {', '.join(w['basket'])}. {w['source']}. Пусната на {w['built']}.", "",
         "| седмицата до | гледания | промяна за 4 седмици | пазарът | промяна на пазара |", "|---|---|---|---|---|"]
    for i, r in enumerate(step[-16:]):
        j = len(step) - 16 + i if len(step) > 16 else i
        ch = "" if j == 0 else f"{pct(tot[j - 1], tot[j]):+.1f}%"
        mch = "" if j == 0 or not mk[j - 1] or not mk[j] else f"{pct(mk[j - 1], mk[j]):+.1f}%"
        L.append(f"| {r['week_end']} | {r['total']:,} | {ch} | {'' if mk[j] is None else f'{mk[j]:.1f}'} | {mch} |".replace(",", " "))
    L += ["", f"(показани последните 16 точки от {len(step)}; мерките са върху всички)", "",
          f"Мерките: смени на посоката {v['turns']}; размах {v['range_vs_median']:.0%} от медианата; корелация на "
          f"4-седмичните промени с пазарната стрелка {v['corr_with_market']}. Мърда: {'да' if v['moves'] else 'не'}. "
          f"Не повтаря цената: {'да' if v['not_price'] else 'не'}.", ""]
    for q in qvals:              # за таблицата „със и без“: средно на седмица в тримесечието (12 или 13 седмици)
        s0, e0 = s.qend(q) - timedelta(days=89), s.qend(q)
        vals = [r["total"] for r in rows if s0.isoformat() <= r["week_end"] <= e0.isoformat()]
        qvals[q]["wiki"] = sum(vals) / len(vals) if len(vals) >= 12 else None
    return L, v


def with_without(qvals, keys_extra):
    """Историята в датата „важи от“ на последните 8 тримесечия: s1+капекс и с всяка проба поотделно."""
    def base_of(k):
        """2023Q1, а за серия, която започва по-късно, първото ѝ пълно тримесечие."""
        return next((q for q in sorted(qvals) if qvals[q].get(k) is not None), None)

    def idx(q, keys):
        logs = []
        for k in keys:
            b = base_of(k)
            if b is None or qvals.get(q, {}).get(k) is None:
                return None
            logs.append(math.log(100 * qvals[q][k] / qvals[b][k]))
        return math.exp(sum(logs) / len(logs))
    qs = sorted(qvals)[-8:]
    head = "| тримесечие | важи от | историята (S-1, капекс) | " + " | ".join(f"с {n}" for n, _ in keys_extra) + " |"
    L = ["## Историята със и без пробата (последните 8 тримесечия)", "",
         "База 2023Q1 = 100. Пробата влиза като трета съставка; думите са по тримесечието на подаване, "
         "Wikipedia е средното на седмица за тримесечието. Стойността важи от края на тримесечието + 45 дни.",
         "Базата на всяка съставка: " + ", ".join(f"{n} {base_of(k) or 'няма'}" for n, k in
                                               [("S-1", "s1"), ("капекс", "capex")] + [(n, k) for n, k in keys_extra])
         + " (серия, която започва след 2023Q1, е на 100 в първото си пълно тримесечие).", "",
         head, "|" + "---|" * (3 + len(keys_extra))]
    for q in qs:
        b = idx(q, ["s1", "capex"])
        cells = [f"{idx(q, ['s1', 'capex', k]):.1f}" if idx(q, ["s1", "capex", k]) is not None else "няма" for _, k in keys_extra]
        L.append(f"| {q} | {s.effective(q)} | {'няма' if b is None else f'{b:.1f}'} | " + " | ".join(cells) + " |")
    return L + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts-dir")
    a = ap.parse_args()
    if a.facts_dir:
        fs.FACTS_DIR = Path(a.facts_dir)
        fs.load.cache_clear()
    mlev = market_levels()
    last_fri = max(mlev)
    qvals = s.history_quarters(s.expected_quarter(last_fri))
    L = ["# Пробите на ПРОЛЕТР9: AI думите и вниманието от Wikipedia", "",
         f"Сметнато на {date.today().isoformat()} от `src/v2/probe_report.py`; пазарната стрелка до петък {last_fri}.", "",
         f"Мярката (Ц., 27.11.2026): мърда = поне {MIN_TURNS} смени на посоката и размах поне {MIN_RANGE:.0%} от медианата; "
         f"не повтаря цената = |корелация| под {MAX_CORR}. Серия без „да“ на Ц. не влиза.", ""]
    lw, vw = words_section(mlev, qvals)
    lk, vk = wiki_section(mlev, qvals)
    L += lw + lk + with_without(qvals, [("думите", "words"), ("Wikipedia", "wiki")])
    out = PROBES / "probe_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"[probe_report] думите: {vw} | wikipedia: {vk} -> {out}")


if __name__ == "__main__":
    main()
