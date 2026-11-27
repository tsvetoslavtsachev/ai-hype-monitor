"""
strelki_site.py: публичната страница на AI Hype с двете стрелки (ПРОЛЕТР9).
=============================================================================
Решение на Ц. (27.11.2026): таблото е на публичния сайт на монитора (GitHub Pages от main/docs),
на мястото на замразеното лице; седмичният ход го обновява сам. Старото лице е в
docs/arhiv/2026-11-20/index.html, каквото е било на 20.11.2026.

Входове: out/weekly/<събота>.json (strelki.py) и out/weekly/strelki_series.csv.
Изходи:  docs/index.html (самостоятелна страница, данните са вътре) и docs/data/strelki_series.csv
         (същата серия за сваляне).

Страницата само показва числата от двата файла: не смята нищо, което strelki.py не е сметнал,
освен форматирането. Без зони, без цвят за „добро/лошо“, без прогноза (решенията на ПРОЛЕТМ2).
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
SERIES = "strelki_series.csv"
CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"

SEG_BG = {"AI Software": "AI софтуер", "Chip Design": "Дизайн на чипове", "Hyperscalers": "Хайпърскейлъри",
          "Infrastructure & Power": "Инфраструктура и енергия", "Memory & Storage": "Памет и съхранение",
          "Networking & Optics": "Мрежи и оптика", "Semiconductor Equipment": "Оборудване за чипове"}
PART_BG = {"s1": ("Новите компании", "делът на проспектите за листване (S-1) със „artificial intelligence“"),
           "capex": ("Парите", "капиталовите разходи на Microsoft, Alphabet, Amazon, Meta и Oracle към продажбите им"),
           "words": ("Думите", "делът на съобщенията за резултати (8-K), в които се казва „artificial intelligence“")}


def dm(d, year=True):
    return f"{d[8:10]}.{d[5:7]}.{d[0:4]}" if year else f"{d[8:10]}.{d[5:7]}"


def num(x, nd=0):
    if x is None:
        return "няма"
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def pct(x):
    if x is None:
        return "няма"
    return ("+" if x > 0 else "") + num(x, 1) + "%"


def esc(s):
    return html.escape(str(s), quote=True)


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


def kpi(label, level, lines):
    sub = "".join(f'<div class="sub">{esc(x)}</div>' for x in lines)
    return f'<div class="kpi"><div class="lbl">{esc(label)}</div><div class="val">{num(level)}</div>{sub}</div>'


def render(o, rows):
    m, h = o["market"], o["history"]
    fri = o["friday"]
    m_lines = [f"седмица {pct(m['vs_1_week']['change_pct'])} · месец {pct(m['vs_4_weeks']['change_pct'])} · "
               f"година {pct(m['vs_52_weeks']['change_pct'])}",
               f"върхът {num(m['peak']['level'])} на {dm(m['peak']['date'])}, днес {pct(m['peak']['distance_pct'])} от него"]
    parts = h["parts"]
    q = next((p.get("quarter") for p in parts if p.get("quarter")), None)
    vf = next((p.get("valid_from") for p in parts if p.get("valid_from")), None)
    peak_h = ("на върха си" if h["peak"]["distance_pct"] == 0
              else f"върхът {num(h['peak']['level'])} на {dm(h['peak']['date'])}")
    h_lines = [f"тримесечие {q or 'няма'}, важи от {dm(vf) if vf else 'няма'} · съставки {h['components']}",
               f"месец {pct(h['vs_4_weeks']['change_pct'])} · година {pct(h['vs_52_weeks']['change_pct'])} · {peak_h}"]
    missing = [s["short"] + " (" + s["state"] + ")" for s in h.get("stale_or_missing") or []]

    prow = []
    for p in parts:
        name, what = PART_BG.get(p["key"], (p["key"], p.get("label", "")))
        if p.get("index") is None:
            prow.append(f"<tr><td>{esc(name)}</td><td>{esc(what)}</td><td class='n'>няма</td><td>{esc(p['state'])}</td></tr>")
            continue
        val = num(p["value"], 1) + "%" if p["key"] == "capex" else num(p["value"] * 100, 1) + "%"
        base = num(p["base_value"], 1) + "%" if p["key"] == "capex" else num(p["base_value"] * 100, 1) + "%"
        prow.append(f"<tr><td>{esc(name)}</td><td>{esc(what)}</td><td class='n'>{num(p['index'])}</td>"
                    f"<td>{esc(p['quarter'])}: {val} (база {esc(p['base_quarter'])}: {base})</td></tr>")

    srow = []
    for s in o["segments"]:
        srow.append(f"<tr><td>{esc(SEG_BG.get(s['segment'], s['segment']))}</td><td class='n'>{num(s['median_ps'], 2)}</td>"
                    f"<td class='n'>{s['n_names']}</td><td class='n'>{pct(s['vs_4_weeks_pct'])}</td>"
                    f"<td class='n'>{pct(s['vs_52_weeks_pct'])}</td></tr>")

    data = {"d": [r["friday"] for r in rows],
            "m": [round(float(r["market"]), 1) for r in rows],
            "h": [round(float(r["history"]), 1) if r["history"] else None for r in rows]}
    miss_html = (f'<p class="note">Съставка, която липсва или е остаряла: {esc(", ".join(missing))}.</p>'
                 if missing else "")

    return TEMPLATE.format(
        fri=dm(fri), sat=esc(o["saturday"]), base=dm(o["base_week"]), n_names=m["n_names"],
        kpis=kpi("Пазарът", m["level"], m_lines) + kpi("Историята", h["level"], h_lines),
        miss=miss_html, parts="".join(prow), segs="".join(srow),
        median=num(m["median_ps"], 2), base_median=num(m["base_median_ps"], 2),
        data=json.dumps(data, separators=(",", ":")), chart_js=CHART_JS, series=SERIES,
    )


TEMPLATE = """<!doctype html>
<html lang="bg">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AI Hype: двете стрелки, седмицата до {fri}</title>
<style>
:root{{--bg:#fcfcfb;--panel:#ffffff;--ink:#0b0b0b;--sec:#52514e;--muted:#6f6d68;--line:#e1e0d9;--tile:#f1f0ec;--m:#2a78d6;--h:#eb6834;--link:#185fa5}}
@media (prefers-color-scheme: dark){{:root{{--bg:#151515;--panel:#1c1c1b;--ink:#f0efec;--sec:#c3c2b7;--muted:#9a988f;--line:#2c2c2a;--tile:#232322;--m:#3987e5;--h:#d95926;--link:#85b7eb}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
.wrap{{max-width:880px;margin:0 auto;padding:28px 20px 64px}}
h1{{font-size:22px;font-weight:500;margin:0 0 4px}} h2{{font-size:18px;font-weight:500;margin:32px 0 8px}}
.asof{{color:var(--sec);font-size:14px;margin:0 0 20px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:0 0 20px}}
.kpi{{background:var(--tile);border-radius:8px;padding:16px}}
.kpi .lbl{{font-size:14px;color:var(--sec)}} .kpi .val{{font-size:40px;font-weight:500;line-height:1.2;font-variant-numeric:tabular-nums}}
.kpi .sub{{font-size:13px;color:var(--sec)}}
.legend{{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--sec);margin:0 0 6px}}
.legend span{{display:flex;align-items:center;gap:6px}} .sw{{width:20px;height:0;border-top:2px solid var(--m)}} .sw.h{{border-top:2px dashed var(--h)}}
.chart{{position:relative;height:360px}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th{{text-align:left;font-weight:500;color:var(--sec);border-bottom:1px solid var(--line);padding:6px 8px}}
td{{border-bottom:1px solid var(--line);padding:6px 8px;vertical-align:top}} .n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.note,.foot{{color:var(--sec);font-size:14px}} .foot{{margin-top:32px;border-top:1px solid var(--line);padding-top:12px}}
a{{color:var(--link)}}
.tw{{overflow-x:auto}}
</style>
</head>
<body><div class="wrap">
<h1>AI Hype: двете стрелки</h1>
<p class="asof">Седмицата до петък {fri}. 100 е нивото в седмицата до {base}; 200 значи двойно.</p>
<div class="kpis">{kpis}</div>
{miss}
<div class="legend"><span><i class="sw"></i>Пазарът: колко плаща пазарът (седмично)</span><span><i class="sw h"></i>Историята: колко пари, нови компании и думи (тримесечно)</span></div>
<div class="chart"><canvas id="c" role="img" aria-label="Двете стрелки на AI Hype по седмици от {base} до {fri}">Пазарът и историята по седмици; данните са в таблицата за сваляне.</canvas></div>

<h2>Как се чете</h2>
<p><b>Пазарът</b> е медианата на цена към продажби за последните 12 месеца при {n_names} компании от веригата на изкуствения интелект, към петъка: днес {median}, в базовата седмица {base_median}. Показва колко скъпо пазарът плаща за историята.</p>
<p><b>Историята</b> е средното (геометрично) на три индекса, които мерят колко реално се случва. Мести се веднъж на тримесечие, 45 дни след края му, когато отчетите са подадени; затова между стъпките е равна.</p>
<p class="note">Уредът описва, не прогнозира и не е препоръка за покупка или продажба.</p>

<h2>Историята по съставки</h2>
<div class="tw"><table><tr><th>съставка</th><th>какво мери</th><th class="n">индекс</th><th>последната стойност</th></tr>{parts}</table></div>

<h2>Пазарът по сегменти</h2>
<div class="tw"><table><tr><th>сегмент</th><th class="n">медиана P/S</th><th class="n">имена</th><th class="n">месец</th><th class="n">година</th></tr>{segs}</table></div>

<p class="foot">Данните по седмици: <a href="data/{series}" download>{series}</a>. Източници: SEC EDGAR (финансовите отчети в XBRL и пълнотекстовото търсене), цени от архива на цените и Yahoo Finance, курсът евро/долар за ASML. Обновява се всяка събота. <a href="arhiv/2026-11-20/">Старото лице на монитора</a>, замразено на 20.11.2026.</p>
</div>
<script src="{chart_js}"></script>
<script>
const D={data};
const cs=getComputedStyle(document.documentElement);
const v=n=>cs.getPropertyValue(n).trim();
const dm=s=>s.slice(8,10)+'.'+s.slice(5,7)+'.'+s.slice(0,4);
const f=x=>x==null?'няма':Math.round(x).toString();
new Chart(document.getElementById('c'),{{type:'line',data:{{labels:D.d,datasets:[
{{label:'Пазарът',data:D.m,borderColor:v('--m'),borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0}},
{{label:'Историята',data:D.h,borderColor:v('--h'),borderWidth:2,borderDash:[6,4],stepped:true,pointRadius:0,pointHoverRadius:4}}]}},
options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:i=>dm(D.d[i[0].dataIndex]),label:c=>c.dataset.label+': '+f(c.parsed.y)}}}}}},
scales:{{x:{{grid:{{display:false}},ticks:{{color:v('--muted'),autoSkip:false,maxRotation:0,callback:(t,i)=>(D.d[i].slice(5,7)==='01'&&+D.d[i].slice(8,10)<=7)?D.d[i].slice(0,4):''}}}},
y:{{grid:{{color:v('--line')}},ticks:{{color:v('--muted')}}}}}}}}}});
</script>
</body></html>
"""


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
    od = Path(a.out_dir) if a.out_dir else DOCS
    (od / "data").mkdir(parents=True, exist_ok=True)
    (od / "index.html").write_text(render(o, rows), encoding="utf-8")
    shutil.copyfile(WEEKLY / SERIES, od / "data" / SERIES)
    print(f"[strelki_site] {o['friday']} -> {od / 'index.html'}")


if __name__ == "__main__":
    main()
