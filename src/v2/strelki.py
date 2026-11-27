"""
strelki.py: AI Hype, двете стрелки (ПРОЛЕТР9, Фаза 4).
======================================================
Термометър без таван и без зони. Решено от Ц. на 26.11.2026 (ПРОЛЕТМ2) и 27.11.2026 (ПРОЛЕТР9).

  Пазарът (седмично): колко плаща пазарът за историята. Медианата на цена към продажби
    (P/S за 12 месеца) по всички имена с данни, от multiple_v2.json; сегментите са таблицата
    (ps_by_ticker.json).
  Историята (тримесечно): колко пари се наливат, колко нови компании се закачат и колко
    компаниите говорят за AI. Геометрична средна на три индекса: делът на S-1 проспектите с
    „artificial intelligence“ (froth.json), капексът за 12 месеца на MSFT, GOOGL, AMZN, META и
    ORCL към продажбите им за 12 месеца (app/data/v2/facts) и делът на 8-K съобщенията за
    резултати с „artificial intelligence“ (ai_words.json; третата съставка по решението на Ц.
    „Само думите“ от 27.11.2026; тримесечието е по датата на подаване).

Правила (еталонът на ПРОЛЕТМ2, `prolet/pregledi/materiali/ai_hype_sim1..4.py`):
  - суровите нива, не оценки спрямо историята;
  - всяка съставка е индекс 100 в базовата седмица BASE_WEEK;
  - тримесечна стойност важи от LAG_DAYS след края на тримесечието и никога по-рано;
  - всяка стрелка: ниво, спрямо преди 4 седмици, спрямо преди 52 седмици, върхът с датата му
    и разстоянието до него;
  - липсваща или остаряла съставка не се осреднява мълчаливо: файлът я назовава с датата ѝ,
    а стрелката казва от колко съставки е.

Изход: out/weekly/<събота>.json (за стола „Позициите и потоците“) и out/weekly/<събота>.md
(кратък, на пътя от заключения списък на стола). Пуск: python src/v2/strelki.py <събота>
"""

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import facts_store as fs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "app" / "data" / "v2"
UNIVERSE = ROOT / "config" / "universe.csv"
OUT_DIR = ROOT / "out" / "weekly"

BASE_WEEK = "2023-05-19"      # първата седмица, в която всички съставки са налице (еталонът)
LAG_DAYS = 45                 # тримесечната стойност важи от края + 45 дни
HYPERSCALERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]
FEW_NAMES = 3                 # сегмент с по-малко имена е „малко имена“
WEEKS_MONTH, WEEKS_YEAR = 4, 52

SRC_PS = "app/data/v2/multiple_v2.json (медианата), app/data/v2/ps_by_ticker.json (по име); цени app/data/prices, акции и продажби SEC XBRL companyfacts"
SRC_S1 = "app/data/v2/froth.json (SEC EDGAR full-text search: S-1 и S-1/A с „artificial intelligence“ към всички S-1)"
SRC_CAPEX = "app/data/v2/facts (SEC XBRL companyfacts: капекс и продажби за 12 месеца, по дата на подаване)"
SRC_WORDS = ("app/data/v2/ai_words.json (SEC EDGAR full-text search: 8-K документи с „artificial intelligence“ "
             "и „three months ended“ към тези с „three months ended“, по тримесечието на подаване)")


# ── дати ────────────────────────────────────────────────────────────────────

def qend(q: str) -> date:
    y, k = int(q[:4]), int(q[5])
    nxt = date(y + (k == 4), 1 if k == 4 else 3 * k + 1, 1)
    return nxt - timedelta(days=1)


def effective(q: str) -> str:
    return (qend(q) + timedelta(days=LAG_DAYS)).isoformat()


def quarter_of(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.year}Q{(x.month - 1) // 3 + 1}"


def quarters_from(first: str, last: str):
    y, k = int(first[:4]), int(first[5])
    out = []
    while f"{y}Q{k}" <= last:
        out.append(f"{y}Q{k}")
        y, k = (y + 1, 1) if k == 4 else (y, k + 1)
    return out


def expected_quarter(d: str):
    """Най-новото тримесечие, което трябва да важи към d (край + LAG_DAYS ≤ d)."""
    q = quarter_of(d)
    for qq in reversed(quarters_from("2022Q1", q)):
        if effective(qq) <= d:
            return qq
    return None


# ── съставките ──────────────────────────────────────────────────────────────

def load_json(name):
    return json.loads((V2 / name).read_text(encoding="utf-8"))


def market_series():
    """[(петък, медиана P/S, брой имена)] от multiple_v2.json."""
    return [(r["date"], r["median_ps"], r["n_tickers"]) for r in load_json("multiple_v2.json")["series"]]


def s1_quarters():
    """{тримесечие: (дял, ai_hits, s1_root_filings)} от froth.json."""
    return {r["quarter"]: (r["share"], r.get("ai_hits"), r.get("s1_root_filings"))
            for r in load_json("froth.json")["series"] if r.get("share") is not None}


def words_quarters():
    """{тримесечие на подаване: дял} от ai_words.json."""
    return {r["filing_quarter"]: r["share"] for r in load_json("ai_words.json")["series"] if r.get("share") is not None}


def capex_quarter(q: str):
    """Капекс/продажби за 12 месеца на петте към тримесечието q, както се знае към датата „важи от“.

    Всяко име трябва да има TTM, чийто край е в календарното тримесечие q; иначе връща
    (None, детайли) с назованите имена.
    """
    eff = effective(q)
    det, cap, rev, missing = {}, 0.0, 0.0, []
    for t in HYPERSCALERS:
        c, r = fs.ttm_asof(t, "capex", eff), fs.ttm_asof(t, "revenue", eff)
        ce = max(x["period_end"] for x in c["derived_from"]) if c else None
        re_ = max(x["period_end"] for x in r["derived_from"]) if r else None
        det[t] = {"capex_12m": c["value"] if c else None, "capex_to": ce,
                  "revenue_12m": r["value"] if r else None, "revenue_to": re_}
        if not c or not r or quarter_of(ce) != q or quarter_of(re_) != q:
            missing.append(t)
            continue
        cap += c["value"]
        rev += r["value"]
    if missing:
        return None, {"names": det, "missing": missing}
    return cap / rev * 100, {"names": det, "capex_12m_sum": cap, "revenue_12m_sum": rev}


def history_quarters(last_q: str):
    """{тримесечие: {"s1": ..., "capex": ..., "words": ...}} от 2023Q1 до last_q."""
    s1 = s1_quarters()
    words = words_quarters()
    out = {}
    for q in quarters_from("2023Q1", last_q):
        cx, cdet = capex_quarter(q)
        out[q] = {"s1": s1.get(q, (None, None, None))[0], "s1_counts": s1.get(q, (None, None, None))[1:],
                  "capex": cx, "capex_detail": cdet, "words": words.get(q)}
    return out


def held(qvals: dict, key: str, d: str):
    """Последното тримесечие със стойност за key, което важи към d: (тримесечие, стойност)."""
    best = None
    for q in sorted(qvals):
        if effective(q) <= d and qvals[q][key] is not None:
            best = (q, qvals[q][key])
    return best


# ── стрелките ───────────────────────────────────────────────────────────────

def market_arrow(series):
    """{петък: (индекс, медиана, брой)} от базовата седмица нататък."""
    m = {d: (v, n) for d, v, n in series}
    if m.get(BASE_WEEK, (None,))[0] is None:
        raise SystemExit(f"market: no median P/S in base week {BASE_WEEK}")
    base = m[BASE_WEEK][0]
    return {d: (100 * v / base, v, n) for d, (v, n) in sorted(m.items()) if d >= BASE_WEEK and v is not None}


SHORT = {"s1": "S-1 делът", "capex": "капексът на хайпърскейлърите",
         "words": "AI думите в резултатите"}   # за реда в блока
HIST_KEYS = [("s1","делът на S-1 проспектите с „artificial intelligence“", SRC_S1),
             ("capex", "капексът на петте хайпърскейлъра към продажбите им, %", SRC_CAPEX),
             ("words", "делът на съобщенията за резултати (8-K) с „artificial intelligence“", SRC_WORDS)]


def history_arrow(weeks, qvals):
    """{петък: {"index", "parts": [...], "n_used", "n_total"}}.

    Съставка без стойност към петъка не влиза и е назована; остаряла (по-старо тримесечие от
    очакваното) влиза със стойността си и е назована с тримесечието и датата си.
    """
    base = {k: held(qvals, k, BASE_WEEK) for k, _, _ in HIST_KEYS}
    out = {}
    for d in weeks:
        exp = expected_quarter(d)
        parts, logs = [], []
        for k, label, src in HIST_KEYS:
            h = held(qvals, k, d)
            if h is None or base[k] is None:
                why = "няма стойност към петъка" if h is None else f"няма стойност в базовата седмица {BASE_WEEK}"
                parts.append({"key": k, "label": label, "state": "липсва", "why": why,
                              "expected_quarter": exp, "source": src})
                continue
            q, v = h
            idx = 100 * v / base[k][1]
            state = "свежа" if q == exp else "остаряла"
            parts.append({"key": k, "label": label, "quarter": q, "valid_from": effective(q),
                          "value": v, "base_quarter": base[k][0], "base_value": base[k][1],
                          "index": idx, "state": state, "expected_quarter": exp, "source": src})
            logs.append(math.log(idx))
        out[d] = {"index": math.exp(sum(logs) / len(logs)) if logs else None, "parts": parts,
                  "n_used": len(logs), "n_total": len(HIST_KEYS)}
    return out


def readings(levels: dict, d: str):
    """Ниво, спрямо преди 4 и 52 седмици, върхът с датата и разстоянието (от базата до d)."""
    ds = [x for x in sorted(levels) if x <= d and levels[x] is not None]
    i = ds.index(d)

    def back(w):
        if i - w < 0:
            return None
        d0 = ds[i - w]
        return {"date": d0, "level": round(levels[d0], 2), "change_pct": round((levels[d] / levels[d0] - 1) * 100, 1)}
    pk = max(ds[: i + 1], key=lambda x: levels[x])
    return {"date": d, "level": round(levels[d], 2), "vs_1_week": back(1), "vs_4_weeks": back(WEEKS_MONTH),
            "vs_52_weeks": back(WEEKS_YEAR),
            "peak": {"date": pk, "level": round(levels[pk], 2),
                     "distance_pct": round((levels[d] / levels[pk] - 1) * 100, 1)}}


# ── сегментите и имената ────────────────────────────────────────────────────

def segments(friday: str):
    t = load_json("ps_by_ticker.json")
    weeks = t["weeks"]
    if friday not in weeks:
        raise SystemExit(f"ps_by_ticker.json has no week {friday}")
    i = weeks.index(friday)
    segs = {}
    for tk, v in t["tickers"].items():
        segs.setdefault(v["layer"], []).append(tk)
    rows = []
    for s in sorted(segs):
        names = sorted(segs[s])

        def med(j):
            vals = [t["tickers"][x]["ps"][j] for x in names if j >= 0 and t["tickers"][x]["ps"][j] is not None]
            return (statistics.median(vals), len(vals)) if vals else (None, 0)
        now, n = med(i)
        m4, _ = med(i - WEEKS_MONTH)
        y1, _ = med(i - WEEKS_YEAR)
        rows.append({
            "segment": s, "median_ps": round(now, 2) if now is not None else None, "n_names": n,
            "names": {x: t["tickers"][x]["ps"][i] for x in names},
            "without_data": [x for x in names if t["tickers"][x]["ps"][i] is None],
            "vs_4_weeks_pct": round((now / m4 - 1) * 100, 1) if now and m4 else None,
            "vs_52_weeks_pct": round((now / y1 - 1) * 100, 1) if now and y1 else None,
            "note": "малко имена" if n < FEW_NAMES else None,
        })
    names = []
    for tk, det in sorted(t["last"].items()):
        if t["last_week"] != friday:
            break
        names.append({"ticker": tk, "segment": t["tickers"][tk]["layer"], **det})
    return rows, names


# ── сглобяване ──────────────────────────────────────────────────────────────

def build(saturday: str):
    series = market_series()
    fridays = [d for d, v, _ in series if d <= saturday]
    if not fridays:
        raise SystemExit("no Friday on/before " + saturday)
    friday = fridays[-1]
    mk = market_arrow(series)
    if friday not in mk:
        raise SystemExit(f"market: no median P/S for {friday}")
    weeks = [d for d in sorted(mk) if d <= friday]
    qvals = history_quarters(quarter_of(friday))
    hs = history_arrow(weeks, qvals)

    mlev = {d: mk[d][0] for d in weeks}
    hlev = {d: hs[d]["index"] for d in weeks}
    m_read, h_read = readings(mlev, friday), readings(hlev, friday)
    h_now = hs[friday]
    segs, names = segments(friday)
    stale = [p for p in h_now["parts"] if p["state"] != "свежа"]
    out = {
        "instrument": "AI Hype, двете стрелки",
        "reader": "столът „Позициите и потоците“ (Кръгът)",
        "saturday": saturday, "friday": friday,
        "built_by": "src/v2/strelki.py (ПРОЛЕТР9)",
        "how_to_read": ("Две стрелки без таван. Всяка съставка е 100 в базовата седмица; 288 значи "
                        "2,88 пъти нивото от базовата седмица. Пазарът е седмичен (петъкът); историята е "
                        "тримесечна и всяка тримесечна стойност важи от 45 дни след края на тримесечието. "
                        "„vs_4_weeks“ е спрямо петъка преди 4 седмици, „vs_52_weeks“ спрямо петъка преди 52."),
        "base_week": BASE_WEEK, "lag_days": LAG_DAYS,
        "market": {
            "what": "колко плаща пазарът за историята: медианата на цена към продажби (12 месеца) по имената",
            **m_read,
            "median_ps": round(mk[friday][1], 4), "base_median_ps": round(mk[BASE_WEEK][1], 4),
            "n_names": mk[friday][2], "components": "1 от 1", "source": SRC_PS,
        },
        "history": {
            "what": "колко пари се наливат, колко нови компании се закачат и колко компаниите говорят за AI (тримесечно)",
            **h_read,
            "components": f"{h_now['n_used']} от {h_now['n_total']}",
            "stale_or_missing": [{"label": p["label"], "short": SHORT[p["key"]], "state": p["state"], "quarter": p.get("quarter"),
                                  "valid_from": p.get("valid_from"), "expected_quarter": p.get("expected_quarter")}
                                 for p in stale],
            "parts": h_now["parts"],
            # капексът за очакваното тримесечие: сумите или назованите имена без него
            "capex_detail": {"quarter": expected_quarter(friday),
                             **(qvals.get(expected_quarter(friday), {}).get("capex_detail") or {})},
        },
        "segments": segs,
        "names": names,
        "frozen": ("Зоните, скоростният флаг, разминаването G, сборът E, „обещание срещу доставка“, "
                   "реториката от корпуса и журналът на пукнатините са замразени от ПРОЛЕТР9 "
                   "(решение на Ц., 26.11.2026); данните им остават четими в app/data/v2."),
    }
    return out


SERIES_FILE = "strelki_series.csv"
MD_HEAD = "# AI Hype: двете стрелки"   # така започва нашият .md; друг .md на същия път не се пипа


def series(friday: str):
    """Цялата седмична история на двете стрелки до петъка, ред по петък (за графики и публикации).

    Същите правила като файла за съботата: пазарът от базовата седмица, историята по датата
    „важи от“, сегментите като медиана на P/S по имената им. Колоните са на латиница, за да се
    отварят в Excel без настройка на кодировката.
    """
    mk = market_arrow(market_series())
    weeks = [d for d in sorted(mk) if d <= friday]
    hs = history_arrow(weeks, history_quarters(quarter_of(friday)))
    t = load_json("ps_by_ticker.json")
    segs = {}
    for tk, v in t["tickers"].items():
        segs.setdefault(v["layer"], []).append(tk)
    pos = {d: i for i, d in enumerate(t["weeks"])}
    rows = []
    for d in weeks:
        h = hs[d]
        part = {p["key"]: p for p in h["parts"]}
        row = {"friday": d, "market": round(mk[d][0], 2), "median_ps": round(mk[d][1], 4), "n_names": mk[d][2],
               "history": round(h["index"], 2) if h["index"] is not None else "",
               "history_components": f"{h['n_used']} of {h['n_total']}"}
        for k, _, _ in HIST_KEYS:
            p = part.get(k, {})
            row[f"{k}_index"] = round(p["index"], 2) if p.get("index") is not None else ""
            row[f"{k}_quarter"] = p.get("quarter", "")
        for sname in sorted(segs):
            i = pos.get(d)
            vals = [t["tickers"][x]["ps"][i] for x in segs[sname] if i is not None and t["tickers"][x]["ps"][i] is not None]
            row[f"seg_ps {sname}"] = round(statistics.median(vals), 4) if vals else ""
        rows.append(row)
    return rows


def write_series(rows, path: Path):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ── форматиране ─────────────────────────────────────────────────────────────

def num(x, nd=1):
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s


def pct(x):
    return "няма" if x is None else ("+" if x > 0 else "") + num(x) + "%"


def dm(d):
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}"


def render_md(o):
    m, h = o["market"], o["history"]
    L = [f"{MD_HEAD}, седмицата до петък {dm(o['friday'])}",
         "",
         f"Файлът с всички числа: `out/weekly/{o['saturday']}.json`.",
         "",
         f"Двете стрелки са индекси без таван: 100 е нивото в седмицата до {dm(o['base_week'])}, 200 значи двойно. "
         "Пазарът е медианата на цена към продажби (P/S за 12 месеца) по имената, седмично към петъка. Историята е "
         "геометричната средна на три индекса (S-1 делът, капексът на хайпърскейлърите към продажбите им и делът на "
         "съобщенията за резултати с „artificial intelligence“, по тримесечието на подаване); тя се мести "
         "само когато влезе ново тримесечие (45 дни след края му), затова седмичната ѝ промяна обикновено е 0, а "
         "месечната е стъпката на новото тримесечие.",
         "",
         "| стрелка | ниво | към дата | спрямо 1 седмица | спрямо 4 седмици | спрямо 52 седмици | върхът |",
         "|---|---|---|---|---|---|---|"]

    def ch(r, k):
        return f"{pct(r[k]['change_pct'])} (от {dm(r[k]['date'])})" if r.get(k) else "няма"
    for name, r, when in (("пазарът", m, dm(m["date"])),
                          ("историята", h, f"{max((p['quarter'] for p in h['parts'] if p.get('quarter')), default='?')}, важи от "
                                           f"{dm(max(p['valid_from'] for p in h['parts'] if p.get('valid_from')))}")):
        L.append(f"| {name} | {r['level']:.0f} | {when} | {ch(r, 'vs_1_week')} | {ch(r, 'vs_4_weeks')} | {ch(r, 'vs_52_weeks')} "
                 f"| {r['peak']['level']:.0f} на {dm(r['peak']['date'])} ({pct(r['peak']['distance_pct'])}) |")
    L += ["",
          f"Пазарът: медианата P/S е {num(m['median_ps'], 2)} по {m['n_names']} имена (базата {num(m['base_median_ps'], 2)}). Източник: {m['source']}.",
          f"Историята: от {h['components']} съставки."]
    cd = h.get("capex_detail") or {}
    if cd.get("names"):
        L.append(f"- Капексът за {cd.get('quarter')} по име, до кой край на тримесечието (фискалните краища се различават): "
                 + "; ".join(f"{t} {v['capex_to'] or 'няма'}" for t, v in cd["names"].items()) + ".")
    for p in h["parts"]:
        if p["state"] == "липсва":
            L.append(f"- {p['label']}: липсва. Източник: {p['source']}.")
        else:
            L.append(f"- {p['label']}: {num(p['value'], 4)} за {p['quarter']} (важи от {dm(p['valid_from'])}; база "
                     f"{num(p['base_value'], 4)} за {p['base_quarter']}; индекс {p['index']:.0f}; {p['state']}). Източник: {p['source']}.")
    for s in h["stale_or_missing"]:
        L.append(f"- ВНИМАНИЕ: {s['label']} е {s['state']}: последно {s['quarter']}, очаквано {s['expected_quarter']}.")
    L += ["", "| сегмент | медиана P/S | имена | спрямо 4 седмици | спрямо 52 седмици | без данни |", "|---|---|---|---|---|---|"]
    for s in o["segments"]:
        v = "няма" if s["median_ps"] is None else num(s["median_ps"], 2)
        note = f" ({s['note']})" if s["note"] else ""
        L.append(f"| {s['segment']} | {v}{note} | {s['n_names']} | {pct(s['vs_4_weeks_pct'])} | {pct(s['vs_52_weeks_pct'])} "
                 f"| {', '.join(s['without_data']) or 'няма'} |")
    miss = [f"{n['ticker']} ({n['missing']})" for n in o["names"] if n.get("missing")]
    notes = [f"{n['ticker']}: брой акции от {n['shares_tag'].split(':')[1]}" for n in o["names"]
             if n.get("shares_tag") and not n["shares_tag"].startswith("dei:")]
    L += ["", "Имена без число: " + (", ".join(miss) or "няма") + ".",
          "Акции от резервен таг: " + ("; ".join(notes) or "няма") + ".",
          "", o["frozen"], ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("saturday", nargs="?",
                    help="датата на файла (съботата след петъка на данните), YYYY-MM-DD; "
                         "без нея: съботата след последния петък с медиана в multiple_v2.json")
    ap.add_argument("--print-saturday", action="store_true", help="само печата съботата и спира")
    ap.add_argument("--facts-dir", help="друга папка с фактите (само за сверки)")
    ap.add_argument("--out-dir", help="друга папка за изхода (само за сверки)")
    a = ap.parse_args()
    if a.facts_dir:
        fs.FACTS_DIR = Path(a.facts_dir)
        fs.load.cache_clear()
    if not a.saturday:
        fri = [d for d, v, _ in market_series() if v is not None][-1]
        a.saturday = (date.fromisoformat(fri) + timedelta(days=1)).isoformat()
    if a.print_saturday:
        print(a.saturday)
        return
    o = build(a.saturday)
    od = Path(a.out_dir) if a.out_dir else OUT_DIR
    od.mkdir(parents=True, exist_ok=True)
    (od / f"{a.saturday}.json").write_text(json.dumps(o, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = od / f"{a.saturday}.md"
    if md.exists() and not md.read_text(encoding="utf-8").startswith(MD_HEAD):
        # замразеният едностраничник от старото лице (2026-11-21.md) остава, какъвто го е чел столът
        print(f"[strelki] {md.name}: old one-pager kept, short .md not written")
    else:
        md.write_text(render_md(o), encoding="utf-8")
    write_series(series(o["friday"]), od / SERIES_FILE)
    m, h = o["market"], o["history"]
    print(f"[strelki] {o['friday']}: market {m['level']:.1f} | history {h['level']:.1f} ({h['components']})")


if __name__ == "__main__":
    main()
