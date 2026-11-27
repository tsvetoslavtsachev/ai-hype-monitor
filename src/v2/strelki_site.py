"""
strelki_site.py: публичната страница на AI Hype с двете стрелки (ПРОЛЕТР9).
=============================================================================
Решения на Ц. (27.11.2026): таблото е на публичния сайт на монитора (GitHub Pages от main/docs),
на мястото на замразеното лице, и е „на нивото на най-добрите финансови сайтове“: главна графика
с избор на период и спад от върха, сегментите като сравнение, малки графики и имената им,
съставките на историята, ръководство за четене, данни за сваляне и графики като картинка.
Старото лице е в docs/arhiv/2026-11-20/index.html, каквото е било на 20.11.2026.

Входове: out/weekly/<събота>.json (strelki.py), out/weekly/strelki_series.csv,
         app/data/v2/ps_by_ticker.json (P/S по име), app/data/prices/<T>.json (името на компанията).
Изходи:  docs/index.html (шаблонът src/v2/site/index.template.html с данните вътре),
         docs/data/strelki_series.csv и docs/data/latest.json (за сваляне).

Страницата само показва числата от тези файлове: не смята нищо ново освен форматирането и
производните за показване (спад от върха, промяна за период). Без зони, без цвят за „добро/лошо“,
без прогноза (решенията на ПРОЛЕТМ2).
"""

import argparse
import csv
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEEKLY = ROOT / "out" / "weekly"
DOCS = ROOT / "docs"
V2 = ROOT / "app" / "data" / "v2"
PRICES = ROOT / "app" / "data" / "prices"
TEMPLATE = Path(__file__).resolve().parent / "site" / "index.template.html"
SERIES = "strelki_series.csv"
LATEST = "latest.json"

SEG_BG = {"AI Software": "AI софтуер", "Chip Design": "Дизайн на чипове", "Hyperscalers": "Хайпърскейлъри",
          "Infrastructure & Power": "Инфраструктура и енергия", "Memory & Storage": "Памет и съхранение",
          "Networking & Optics": "Мрежи и оптика", "Semiconductor Equipment": "Оборудване за чипове"}
PART_BG = {"s1": ("Новите компании", "делът на проспектите за листване (S-1), в които пише „artificial intelligence“"),
           "capex": ("Парите", "капиталовите разходи на Microsoft, Alphabet, Amazon, Meta и Oracle към продажбите им"),
           "words": ("Думите", "делът на съобщенията за тримесечни резултати (8-K), в които пише „artificial intelligence“")}


def dm(d):
    return f"{d[8:10]}.{d[5:7]}.{d[0:4]}"


def num(x, nd=0):
    if x is None:
        return "няма"
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def latest_saturday():
    files = sorted(p.stem for p in WEEKLY.glob("????-??-??.json"))
    if not files:
        raise SystemExit("no out/weekly/<saturday>.json")
    return files[-1]


def read_series(path: Path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{path} is empty")
    return rows


def fl(x, nd=2):
    return round(float(x), nd) if x not in ("", None) else None


def company(t):
    p = PRICES / f"{t}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("name") or t
    return t


def build_data(o, rows, ps):
    """Всичко, което страницата рисува: от файла за съботата, серията и P/S по име."""
    d = [r["friday"] for r in rows]
    segs = sorted({k[len("seg_ps "):] for k in rows[0] if k.startswith("seg_ps ")})
    series = {
        "d": d,
        "m": [fl(r["market"], 1) for r in rows],
        "h": [fl(r["history"], 1) for r in rows],
        "s1": [fl(r["s1_index"], 1) for r in rows],
        "capex": [fl(r["capex_index"], 1) for r in rows],
        "words": [fl(r["words_index"], 1) for r in rows],
        "hq": [r["capex_quarter"] or r["s1_quarter"] for r in rows],
        "median": [fl(r["median_ps"], 3) for r in rows],
        "seg": {s: [fl(r[f"seg_ps {s}"], 2) for r in rows] for s in segs},
    }
    pos = {w: i for i, w in enumerate(ps["weeks"])}
    names = {}
    for t, v in sorted(ps["tickers"].items()):
        names[t] = {"name": company(t), "seg": v["layer"],
                    "ps": [round(v["ps"][pos[w]], 2) if w in pos and v["ps"][pos[w]] is not None else None for w in d],
                    "missing": (ps.get("last") or {}).get(t, {}).get("missing")}
    m, h = o["market"], o["history"]
    parts = []
    for p in h["parts"]:
        name, what = PART_BG.get(p["key"], (p["key"], p.get("label", "")))
        parts.append({"key": p["key"], "name": name, "what": what, "state": p["state"],
                      "quarter": p.get("quarter"), "valid_from": p.get("valid_from"),
                      "index": round(p["index"], 1) if p.get("index") is not None else None,
                      "value": p.get("value"), "base_value": p.get("base_value"), "base_quarter": p.get("base_quarter")})
    return {
        "friday": o["friday"], "saturday": o["saturday"], "base": o["base_week"], "lag": o.get("lag_days", 45),
        "market": {k: m.get(k) for k in ("level", "median_ps", "base_median_ps", "n_names",
                                          "vs_1_week", "vs_4_weeks", "vs_52_weeks", "peak")},
        "history": {k: h.get(k) for k in ("level", "components", "vs_1_week", "vs_4_weeks", "vs_52_weeks", "peak")},
        "missing": [s["short"] + " (" + s["state"] + ")" for s in h.get("stale_or_missing") or []],
        "parts": parts,
        "segments": [{"key": s["segment"], "bg": SEG_BG.get(s["segment"], s["segment"]), "median": s["median_ps"],
                      "n": s["n_names"], "m4": s["vs_4_weeks_pct"], "y1": s["vs_52_weeks_pct"]} for s in o["segments"]],
        "series": series, "names": names,
    }


def render(o, rows, ps):
    data = build_data(o, rows, ps)
    m, h = o["market"], o["history"]
    q = next((p["quarter"] for p in data["parts"] if p.get("quarter")), "няма")
    subs = {
        "__FRIDAY__": dm(o["friday"]),
        "__BASE__": dm(o["base_week"]),
        "__M_LEVEL__": num(m["level"]),
        "__H_LEVEL__": num(h["level"]),
        "__H_COMPONENTS__": html.escape(h["components"]),
        "__H_QUARTER__": html.escape(q),
        "__N_NAMES__": str(m["n_names"]),
        # </ в JSON не трябва да затваря <script>
        "__DATA__": json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    }
    page = TEMPLATE.read_text(encoding="utf-8")
    for k, v in subs.items():
        if k not in page:
            raise SystemExit(f"template has no {k}")
        page = page.replace(k, v)
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("saturday", nargs="?", help="съботата на файла; без нея: последният в out/weekly")
    ap.add_argument("--out-dir", help="друга папка вместо docs (само за проверки)")
    a = ap.parse_args()
    sat = a.saturday or latest_saturday()
    o = json.loads((WEEKLY / f"{sat}.json").read_text(encoding="utf-8"))
    rows = read_series(WEEKLY / SERIES)
    if rows[-1]["friday"] != o["friday"]:
        raise SystemExit(f"series ends {rows[-1]['friday']}, file is for {o['friday']}: run strelki.py first")
    ps = json.loads((V2 / "ps_by_ticker.json").read_text(encoding="utf-8"))
    od = Path(a.out_dir) if a.out_dir else DOCS
    (od / "data").mkdir(parents=True, exist_ok=True)
    (od / "index.html").write_text(render(o, rows, ps), encoding="utf-8")
    shutil.copyfile(WEEKLY / SERIES, od / "data" / SERIES)
    shutil.copyfile(WEEKLY / f"{sat}.json", od / "data" / LATEST)
    print(f"[strelki_site] {o['friday']} -> {od / 'index.html'}")


if __name__ == "__main__":
    main()
