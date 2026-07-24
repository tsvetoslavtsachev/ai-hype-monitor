"""
render_onepager_html.py — човешкото v2 лице (docs/index.html).
=============================================================
Детерминистичен рендер. Чете СЪЩИТЕ входове като onepager.py (gap_series,
zones_retro, euphoria_series, froth, tripwires) и произвежда docs/index.html:
изводът първо (човешки, ФОРМУЛИРАН ОТ ДАННИТЕ), зоната като светофар,
журналът на пукнатините като разказ с външни линкове, механиката в сгъвка
<details> с provenance-таблица идентична на .md едностраничника.

КАНОН (ФОРМА-КАНОН §1): изводът първо · всяко име линк навън · всеки термин с
tooltip · видима as-of дата · О4 бадж "наблюдение, не сигнал".

Числата са 1:1 с out/weekly/<as_of>.md — същата екстракция, същото форматиране
(функцията f()). Не пипа src/v2 изчисленията; чисто презентационен слой.

M20-FIX1: главният изглед говори консервативен финансово-икономически регистър;
σ-числата слизат в плаващи менюта (styled popovers, hover+focus+click), а текстът
ползва детерминистична градационна z-скала. Сгъвката остава техничен дом на σ/z.
M20-FIX2: нова сгъвка "Рутината" (операторският наръчник + Perplexity промпт с
копи-бутон). И двете — чисто презентация, без докосване на данни/прагове.
"""

import html
import json
import re
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from onepager import _last_defined, AS_OF  # noqa: E402  (споделен източник, без дублиране)

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "app" / "data" / "v2"
DOCS = ROOT / "docs"

# Новото публично лице е предвидено да живее на site-root — препоръка:
# GitHub Pages → Deploy from a branch → main → /docs (прави docs/index.html корен).


# ─────────────────────────── форматиране ────────────────────────────
def f(x):
    """ТОЧНО както onepager.py — гарантира 1:1 стойности с .md."""
    return "None" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))


def sig(x):
    """Човешки signed sigma: +4.04σ / -2.26σ / None."""
    if x is None:
        return "n/a"
    return f"{x:+.2f}σ"


def esc(s):
    return html.escape("" if s is None else str(s))


# ───────────────── градационна z-скала (M20-FIX1 §3) ─────────────────
# Детерминистична: числото е на един hover разстояние (в плаващото меню),
# а видимият текст носи фиксираната формулировка. Замразена в този fix.
def gradation(z):
    """Пълна формулировка по |z| (за изречения в главния изглед)."""
    if z is None:
        return "без актуално показание"
    a = abs(z)
    if a < 1.0:
        return "в рамките на историческата норма"
    pos = z > 0
    if a < 2.0:
        return "над историческата норма" if pos else "под историческата норма"
    if a < 3.0:
        return ("съществено над историческата норма" if pos
                else "съществено под историческата норма")
    return ("на исторически екстремум (връх) спрямо собствената история" if pos
            else "на исторически екстремум (дъно) спрямо собствената история")


def gradation_chip(z):
    """Компактна градация за чиповете (напр. „исторически връх")."""
    if z is None:
        return "без показание"
    a = abs(z)
    if a < 1.0:
        return "в историческата норма"
    pos = z > 0
    if a < 2.0:
        return "над нормата" if pos else "под нормата"
    if a < 3.0:
        return "съществено над нормата" if pos else "съществено под нормата"
    return "исторически връх" if pos else "историческо дъно"


# ─────────────── плаващо меню (styled popover, M20-FIX1 §2) ──────────
def popover(anchor_html, card_html, aria="детайли", cls=""):
    """Самодостатъчно плаващо меню: hover + focus (tabindex) + click/touch (JS).
    anchor_html = видимият текст (HTML); card_html = съдържанието на менюто (HTML)."""
    return (f'<span class="pop {cls}" tabindex="0" role="button" aria-label="{esc(aria)}">'
            f'<span class="pop-anchor">{anchor_html}</span>'
            f'<span class="pop-card" role="tooltip">{card_html}</span></span>')


def _voice_card(z):
    """Съдържание на плаващото меню за компонентен глас (σ живее ТУК)."""
    return (f'<span class="pop-val">z = {esc(sig(z))}</span>'
            f'<span class="pop-desc">робастен z спрямо собствената ретро-история</span>'
            f'<span class="pop-src">източник: euphoria_series.json</span>')


# ─────────────────────── линкове навън (канон §1.2) ─────────────────
# Куриран речник: тикер → Finviz; частна/лице → новинарски търсещ линк.
_ENTITIES = [
    ("Meta Compute", "ticker", "META"),
    ("Meta", "ticker", "META"),
    ("Microsoft", "ticker", "MSFT"),
    ("MSFT", "ticker", "MSFT"),
    ("Nvidia", "ticker", "NVDA"),
    ("NVDA", "ticker", "NVDA"),
    ("CoreWeave", "ticker", "CRWV"),
    ("SpaceX", "news", "SpaceX AI compute capacity"),
    ("Anthropic", "news", "Anthropic compute deal"),
    ("Reflection", "news", "Reflection AI Colossus GB300"),
    ("Zuckerberg", "news", "Zuckerberg AI progress town hall"),
    ("SemiAnalysis", "news", "SemiAnalysis GPU rental index"),
]


def _entity_href(kind, target):
    if kind == "ticker":
        return f"https://finviz.com/quote.ashx?t={target}"
    q = urllib.parse.quote(target)
    return f"https://news.google.com/search?q={q}"


def linkify(text):
    """HTML-escape + обгради известните имена в <a> навън. Един проход, longest-first."""
    escaped = esc(text)
    # ключовете вече са escaped-safe (ASCII); подреждаме по дължина низходящо
    keys = sorted(_ENTITIES, key=lambda e: -len(e[0]))
    pattern = re.compile("|".join(re.escape(k[0]) for k in keys))
    lookup = {k[0]: (k[1], k[2]) for k in keys}

    def repl(m):
        disp = m.group(0)
        kind, target = lookup[disp]
        href = _entity_href(kind, target)
        title = ("Finviz: " + target) if kind == "ticker" else ("Новини: " + target)
        return (f'<a class="ext" href="{esc(href)}" target="_blank" rel="noopener" '
                f'title="{esc(title)}">{esc(disp)}</a>')

    return pattern.sub(repl, escaped)


def term(label, tip):
    """Термин с tooltip на място (канон §1.3)."""
    return f'<abbr class="term" title="{esc(tip)}">{esc(label)}</abbr>'


# ─────────────────── изводът-първо, формулиран ОТ ДАННИТЕ ────────────
# M20-FIX1 §4.1 — консервативен финансово-икономически регистър (без метафори).
LEASH = {
    "extreme_high": ("Разминаването между пазарния ентусиазъм и фундаменталните показатели е "
                     "на исторически връх — индикаторът показва еуфория."),
    "mild_high": ("Пазарният ентусиазъм изпреварва фундаменталните показатели — разминаването "
                  "е над историческата норма."),
    "neutral": ("Пазарният ентусиазъм и фундаменталните показатели са в равновесие — "
                "индикаторът не показва еуфория."),
    "mild_low": ("Фундаменталните показатели изпреварват пазарния ентусиазъм — разминаването "
                 "е под историческата норма."),
    "extreme_low": ("Фундаменталните показатели далеч изпреварват пазарния ентусиазъм — "
                    "разминаването е на историческо дъно."),
    "undefined": ("Индикаторът е без актуално показание — данните не са обновявани 4+ седмици."),
}

# всеки Е-глас: (ключ, pos-фраза, neg-фраза). Positive z = повече еуфория.
# M20-FIX1 §4.2 — видимата част БЕЗ σ; σ отива в плаващото меню на термина.
# {deg} = пълната градация по §3 (само z_multiple я ползва).
_VOICES = {
    "z_multiple": ("оценъчните множители са {deg}",
                   "оценъчните множители са {deg}"),
    "z_froth": ("делът на нови емисии (IPO проспекти) с AI тематика е повишен",
                "делът на нови емисии (IPO проспекти) с AI тематика е понижен"),
    "z_rhetoric": ("AI реториката в корпоративните отчети е засилена",
                   "AI реториката в корпоративните отчети е приглушена"),
    "z_promise_delivery": ("езикът на обещанията изпреварва отчетената доставка",
                           "корпоративният език е насочен към отчетени резултати, не към обещания"),
}
# _VOICE_LABEL — ОРИГИНАЛНИ етикети за КОМПОНЕНТНАТА ТАБЛИЦА в сгъвката
# (§1 забранява пипането ѝ; затова се пазят непроменени).
_VOICE_LABEL = {
    "z_multiple": "оценъчен множител",
    "z_froth": "пяна по ръбовете",
    "z_rhetoric": "реторика",
    "z_promise_delivery": "обещание/доставка",
}
# _CHIP_LABEL — консервативните етикети за чиповете в главния изглед (§4.3).
_CHIP_LABEL = {
    "z_multiple": "оценъчен множител",
    "z_froth": "нови емисии (IPO)",
    "z_rhetoric": "корпоративна реторика",
    "z_promise_delivery": "обещания/резултати",
}


def _voice_phrase(key, z):
    pos, neg = _VOICES[key]
    tmpl = pos if z >= 0 else neg
    return tmpl.format(deg=gradation(z))   # неизползван {deg} се игнорира тихо


def _voice_pop(key, z):
    """Фразата на глас, обвита в плаващо меню, носещо точното σ."""
    return popover(esc(_voice_phrase(key, z)), _voice_card(z), aria=_CHIP_LABEL[key])


def build_conclusion(zone, gz, erow, fq):
    """Два реда човешки текст (HTML), изведени от зоната + вътрешното разминаване.
    Връща HTML — σ-числата слизат в плаващи менюта (M20-FIX1 §4.4)."""
    head = LEASH.get(zone, LEASH["undefined"])

    voices = [(k, erow.get(k)) for k in _VOICES if erow.get(k) is not None]
    if not voices:
        return esc(head) + " Компонентните показатели липсват за тази седмица."
    loud_key, loud_z = max(voices, key=lambda kv: abs(kv[1]))
    phrase_pop = _voice_pop(loud_key, loud_z)

    F = fq.get("F")
    zrev, zmar = fq.get("z_revenue_growth_yoy"), fq.get("z_operating_margin")
    zvals = [z for z in (zrev, zmar) if z is not None]
    weaker = min(zvals, key=abs) if zvals else None          # общата градация по по-слабия z
    fund_card = (f'<span class="pop-val">приходен ръст z = {esc(sig(zrev))} · '
                 f'оперативен марж z = {esc(sig(zmar))}</span>'
                 f'<span class="pop-desc">робастен z спрямо собствената ретро-история</span>'
                 f'<span class="pop-src">източник: gap_series.json (f_quarterly)</span>')
    fund_pop = popover(esc(f"приходният ръст и оперативният марж са {gradation(weaker)}"),
                       fund_card, aria="фундаментални показатели")

    if abs(loud_z) < 1.0:
        s2 = "Няма открояващи се компоненти — всички са в рамките на историческите си норми."
    elif loud_z > 0:
        s2 = "Един компонент обаче се откроява — " + phrase_pop
        if F is not None and F >= 0.5 and zone in ("neutral", "mild_low", "extreme_low"):
            s2 += (" — а композитът остава в равновесие, защото фундаментът се движи "
                   "успоредно (" + fund_pop + ").")
        elif F is not None and F < 0:
            s2 += " — а фундаментът не помага (" + fund_pop + ")."
        else:
            s2 += "."
    else:
        s2 = "Най-открояващият се компонент е с обратен знак — " + phrase_pop + "."
    return esc(head) + " " + s2


# ─────────────────────── зона: цвят + значение ──────────────────────
ZONE_COLOR = {
    "extreme_high": "#dc2626", "mild_high": "#f97316", "neutral": "#16a34a",
    "mild_low": "#0ea5e9", "extreme_low": "#2563eb", "undefined": "#6b7280",
}
# M20-FIX1 §4.5 — консервативни, БЕЗ σ в текста (σ-диапазонът → плаващо меню).
ZONE_MEANING = {
    "extreme_high": "Ентусиазмът е далеч над фундамента — исторически връх на разминаването.",
    "mild_high": "Ентусиазмът изпреварва фундамента.",
    "neutral": "Ентусиазъм и фундамент са в равновесие.",
    "mild_low": "Фундаментът изпреварва ентусиазма.",
    "extreme_low": "Фундаментът е далеч над ентусиазма.",
    "undefined": "Показанието е застояло (4+ седмици без обновяване).",
}
# Видимите думи на зоната (машинните id-та НЕ се пипат) — §4.5.
DISPLAY_ZONE = {
    "extreme_low": "Екстремно ниско", "mild_low": "Под нормата", "neutral": "Неутрална",
    "mild_high": "Повишено", "extreme_high": "Екстремно високо", "undefined": "Без показание",
}
DISPLAY_ZONE_SHORT = {
    "extreme_low": "Екстр. ниско", "mild_low": "Под нормата", "neutral": "Неутрална",
    "mild_high": "Повишено", "extreme_high": "Екстр. високо",
}
# σ-диапазонът на всяка зона (за плаващото меню; праговете a=1.0, b=2.0 са замразени).
ZONE_SIGMA = {
    "extreme_high": "G_z ≥ +2σ", "mild_high": "G_z между +1σ и +2σ",
    "neutral": "G_z между −1σ и +1σ", "mild_low": "G_z между −2σ и −1σ",
    "extreme_low": "G_z ≤ −2σ", "undefined": "без праг (застояло показание)",
}
ZONE_BOUNDS = {
    "extreme_low": (None, -2.0), "mild_low": (-2.0, -1.0), "neutral": (-1.0, 1.0),
    "mild_high": (1.0, 2.0), "extreme_high": (2.0, None),
}
ZONE_ORDER = ["extreme_low", "mild_low", "neutral", "mild_high", "extreme_high"]


def zone_tercile(zone, gz):
    """Детерминистична позиция в зоната по терцили (M20-FIX1 §4.6)."""
    if gz is None or zone not in ZONE_BOUNDS:
        return "без позиция"
    lo, hi = ZONE_BOUNDS[zone]
    if lo is None:            # extreme_low (отворена надолу) → номинален 1σ пояс
        lo = hi - 1.0
    if hi is None:            # extreme_high (отворена нагоре) → номинален 1σ пояс
        hi = lo + 1.0
    t = (gz - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    if t < 1.0 / 3.0:
        return "в долната част"
    if t < 2.0 / 3.0:
        return "в средната част"
    return "в горната част"


def zone_band_svg(gz, active_zone):
    """Компактен светофар-бар с думите на зоните (§4.5); σ-диапазонът → плаващо меню."""
    segs = [(zk, DISPLAY_ZONE_SHORT[zk]) for zk in ZONE_ORDER]
    w = 100.0 / len(segs)
    cells = []
    for zk, lab in segs:
        op = "1" if zk == active_zone else "0.28"
        cells.append(
            f'<div class="zseg" style="width:{w:.4f}%;background:{ZONE_COLOR[zk]};opacity:{op}" '
            f'title="{esc(DISPLAY_ZONE.get(zk, zk))}"><span>{esc(lab)}</span></div>')
    if gz is None:
        marker = ""
    else:
        pos = max(0.0, min(100.0, (gz + 3.0) / 6.0 * 100.0))
        marker = (f'<div class="zmark" style="left:{pos:.3f}%" '
                  f'title="позиция на индикатора (точната стойност в сгъвката)"></div>')
    band = f'<div class="zband">{"".join(cells)}{marker}</div>'
    legend = ('<span class="pop-val">Прагове по G_z (робастни σ)</span>'
              '<span class="pop-desc">Екстремно ниско: ≤ −2σ · Под нормата: −2…−1σ · '
              'Неутрална: −1…+1σ · Повишено: +1…+2σ · Екстремно високо: ≥ +2σ.</span>'
              '<span class="pop-src">Позиция на индикатора: точната стойност в сгъвката.</span>')
    return popover(band, legend, aria="легенда на зоновата скала", cls="pop--band")


# ─────────────────────────── журналът ───────────────────────────────
def tripwire_card(t, recent):
    tag = '<span class="tw-recent">нова (14 дни)</span>' if recent else ""
    src = linkify(t.get("source", ""))
    return f"""
    <article class="tw-card{' tw-card--recent' if recent else ''}">
      <header class="tw-head">
        <span class="tw-id">{esc(t['id'])}</span>
        <span class="tw-name">{esc(t['name'])}</span>
        {tag}
      </header>
      <p class="tw-what"><span class="tw-when">{esc(t.get('fired_date') or '')}</span> — {src}</p>
      <div class="tw-reads">
        <p class="tw-bear"><span class="tw-lab tw-lab--bear">мечи прочит</span> {esc(t['bearish'])}</p>
        <p class="tw-bull"><span class="tw-lab tw-lab--bull">бичи прочит</span> {esc(t['bullish'])}</p>
      </div>
    </article>"""


def armed_row(t):
    return f"""
      <li class="armed-item">
        <span class="armed-id">{esc(t['id'])}</span>
        <span class="armed-name">{esc(t['name'])}</span>
        <span class="armed-src" title="{esc(t.get('source',''))}">{esc(t.get('source',''))}</span>
      </li>"""


# ─────────────────────────── главният рендер ────────────────────────
def build(as_of=AS_OF):
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
    zone_word = zone_bg.split("(")[-1].rstrip(")") if zone_bg and "(" in zone_bg else zone_bg
    zcolor = ZONE_COLOR.get(zone, "#6b7280")

    # tripwire-ове (СЪЩАТА логика като onepager)
    cutoff = (date.fromisoformat(as_of) - timedelta(days=14)).isoformat()
    fired_all = [t for t in tw["tripwires"] if t["status"] == "fired"]
    fired_recent_ids = {t["id"] for t in fired_all
                        if t["fired_date"] and t["fired_date"] >= cutoff}
    armed = [t for t in tw["tripwires"] if t["status"] != "fired"]

    # provenance (ИДЕНТИЧНА на onepager -> 1:1 с .md)
    prov = [
        ("G_z", grow["G_z"], "app/data/v2/gap_series.json:last(G_z)", wk),
        ("dG4", grow["dG4"], "app/data/v2/gap_series.json:last(dG4)", wk),
        ("G_raw", grow["G_raw"], "app/data/v2/gap_series.json:last(G_raw)", wk),
        ("zone", zone, "app/data/v2/zones_retro.json:committed_zone@" + wk, wk),
        ("velocity_flag", zrow.get("velocity_flag"),
         "app/data/v2/zones_retro.json:velocity_flag@" + wk, wk),
        ("z_rhetoric", erow.get("z_rhetoric"), "euphoria_series.json:z_rhetoric@" + wk, wk),
        ("z_promise_delivery", erow.get("z_promise_delivery"),
         "euphoria_series.json:z_promise_delivery@" + wk, wk),
        ("z_froth", erow.get("z_froth"), "euphoria_series.json:z_froth@" + wk, wk),
        ("z_multiple", erow.get("z_multiple"), "euphoria_series.json:z_multiple@" + wk, wk),
        ("E", erow.get("E"), "euphoria_series.json:E@" + wk, wk),
        ("F", fq["F"], "gap_series.json:f_quarterly:last(F)", fq["quarter"]),
        ("z_revenue_growth_yoy", fq.get("z_revenue_growth_yoy"),
         "gap_series.json:f_quarterly:last", fq["quarter"]),
        ("z_operating_margin", fq.get("z_operating_margin"),
         "gap_series.json:f_quarterly:last", fq["quarter"]),
        ("froth_share", froth_last["share"], "froth.json:last(share)", froth_last["quarter"]),
    ]

    conclusion = build_conclusion(zone, grow["G_z"], erow, fq)

    # ── зона: видима дума + плаващо меню със σ-диапазона (§4.5) ──
    zone_display = DISPLAY_ZONE.get(zone, zone_word)
    zword_card = (f'<span class="pop-val">Праг на зоната «{esc(zone_display)}»</span>'
                  f'<span class="pop-desc">{esc(ZONE_SIGMA.get(zone, "n/a"))} '
                  f'(робастни σ спрямо ретро-историята)</span>'
                  f'<span class="pop-src">източник: zones_retro.json</span>')
    zword_html = popover(esc(zone_display), zword_card, aria="праг на зоната", cls="pop--zword")

    # ── позиционен ред (§4.6): човешки текст + плаващо меню с точните G_z/dG₄/G_raw ──
    vel_txt = "да" if zrow.get("velocity_flag") else "не"
    pos_card = (f'<span class="pop-val">G_z = {esc(f(grow["G_z"]))} ({esc(sig(grow["G_z"]))})</span>'
                f'<span class="pop-desc">dG₄ = {esc(f(grow["dG4"]))} ({esc(sig(grow["dG4"]))}) · '
                f'G_raw = {esc(f(grow["G_raw"]))} · скоростен флаг: {esc(vel_txt)}</span>'
                f'<span class="pop-src">източник: gap_series.json · zones_retro.json</span>')
    position_pop = popover(esc(zone_tercile(zone, grow["G_z"])), pos_card,
                           aria="точни стойности на позицията")
    posline = (f'<p class="posline">Позиция: <strong>{esc(zone_display)}</strong>, '
               f'{position_pop}</p>')

    # ── компоненти: "какво се откроява" стрип (|z| >= 1.5) ──
    notable = []
    for k in _VOICES:
        z = erow.get(k)
        if z is not None and abs(z) >= 1.5:
            notable.append((k, z))
    notable.sort(key=lambda kv: -abs(kv[1]))
    strip = ""
    for k, z in notable:
        col = "#dc2626" if z > 0 else "#16a34a"
        chip = (f'<span class="chip" style="border-color:{col};color:{col}">'
                f'{esc(_CHIP_LABEL[k])} · {esc(gradation_chip(z))}</span>')
        strip += popover(chip, _voice_card(z), aria=_CHIP_LABEL[k], cls="pop--chip")
    if not strip:
        strip = '<span class="chip chip--calm">компонентите са в историческите си норми</span>'

    # ── журнал карти ──
    cards = "".join(tripwire_card(t, t["id"] in fired_recent_ids) for t in fired_all)
    armed_html = "".join(armed_row(t) for t in armed)

    # ── компонентна таблица (в сгъвката) — НЕ се пипа (§1) ──
    comp_rows = ""
    for k in ["z_rhetoric", "z_promise_delivery", "z_froth", "z_multiple"]:
        comp_rows += (f"<tr><td>{esc(_VOICE_LABEL[k])}</td>"
                      f"<td class='num'>{esc(f(erow.get(k)))}</td>"
                      f"<td>{esc(sig(erow.get(k)))}</td></tr>")

    # ── provenance таблица (идентична на .md) ──
    prov_rows = ""
    for m, v, srcp, ka in prov:
        prov_rows += (f"<tr><td>{esc(m)}</td><td class='num'>{esc(f(v))}</td>"
                      f"<td class='src'>{esc(srcp)}</td><td>{esc(ka)}</td></tr>")

    fired_ids = ", ".join(t["id"] for t in fired_all)

    doc = _PAGE.format(
        as_of=esc(as_of), wk=esc(wk),
        conclusion=conclusion,
        o4="наблюдение, не сигнал",
        zone_word=zword_html, zcolor=zcolor,
        zone_meaning=esc(ZONE_MEANING.get(zone, "")),
        zband=zone_band_svg(grow["G_z"], zone),
        posline=posline,
        gz=esc(f(grow["G_z"])), gz_sig=esc(sig(grow["G_z"])),
        dg4=esc(f(grow["dG4"])), dg4_sig=esc(sig(grow["dG4"])),
        vel=vel_txt,
        graw=esc(f(grow["G_raw"])),
        E=esc(f(erow.get("E"))), F=esc(f(fq["F"])),
        strip=strip,
        n_fired=len(fired_all), n_total=len(tw["tripwires"]), fired_ids=esc(fired_ids),
        cards=cards, armed=armed_html,
        term_gz=term("G_z", "Разминаването G = еуфория − фундамент, изразено в робастни σ спрямо собствената му ретро-история."),
        term_dg4=term("dG₄", "Скорост: 4-седмичен наклон на G_z. Само флаг — никога не мести зоната (праг ±1.25σ)."),
        term_e=term("E", "Еуфория: средно на наличните z-гласове (реторика, обещание/доставка, пяна, множител)."),
        term_f=term("F", "Фундамент: средно z на приходен ръст YoY и оперативен марж (TTM, point-in-time)."),
        term_robust=term("робастен z", "Стандартизация чрез медиана и MAD (устойчива на извънредни стойности), разширяващ се прозорец."),
        comp_rows=comp_rows, prov_rows=prov_rows,
        froth_share=esc(f(froth_last["share"])), froth_q=esc(froth_last["quarter"]),
        routine_fold=_ROUTINE_FOLD,
        script=_SCRIPT,
    )

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    out = DOCS / "index.html"
    out.write_text(doc, encoding="utf-8")
    print(f"[render_html] as_of {as_of}, data through {wk}: zone={zone}, "
          f"G_z={f(grow['G_z'])}, fired={len(fired_all)}/{len(tw['tripwires'])} "
          f"-> {out.relative_to(ROOT)}")
    return out, prov


# ───────────── Perplexity промпт (M20-FIX2 §1, Блок 3 — дословно) ─────────────
_PPX_PROMPT = """You are helping me monitor specific warning signs ("tripwires") in the AI
infrastructure sector. Search news from the PAST 7 DAYS and report ONLY items
matching these categories:

T1: A hyperscaler (Microsoft, Google, Meta, Amazon, Oracle, xAI/SpaceX, etc.)
    announcing it is selling or renting out its OWN compute capacity to outside
    customers.
T2: An infrastructure player selling/renting compute capacity directly to AI
    labs (OpenAI, Anthropic, Mistral, etc.).
T3: Three or more players announcing compute-capacity leasing within a 90-day
    window (clustering).
T4: A hyperscaler CEO publicly admitting AI progress or AI benefits are slower
    than expected.
T5: First outright capex CUT (not a slowdown or pause) by a hyperscaler,
    framed as "efficiency".
T6: Sustained decline (more than one quarter) in GPU rental price indices
    (e.g. SemiAnalysis H100 rental index, spot GPU prices).
T7: Reciprocal or round-trip revenue structures in SEC filings: a company
    sells capacity AND simultaneously buys from the same counterparty,
    especially clustered at quarter-end.
T8: An accounting restatement or SEC inquiry/investigation involving an AI
    infrastructure company.
T10: A second hyperscaler REDUCING server/GPU useful-life (depreciation)
     assumptions in its 10-K.
T11: A credit rating downgrade, negative outlook, or watch placement on a
     hyperscaler or AI-infrastructure company explicitly citing AI-related
     leverage, lease obligations, or capex (S&P, Moody's, Fitch actions);
     also material widening in data-center private credit or project bond
     spreads.
T12: New disclosures or third-party studies quantifying growth in
     off-balance-sheet AI obligations: non-commenced data-center leases,
     GPU purchase commitments, SPV/JV financing structures (footnote
     analyses, Moody's/Nikkei-type studies, 10-Q commitment tables).

For every match report: date · source (publication + link) · 2-line summary ·
which tripwire ID it matches · confidence (clear match / borderline).
If nothing matches a category, skip it silently. Exclude general AI hype and
product news. Prefer primary sources: SEC filings, company statements,
Bloomberg, Reuters, FT, WSJ, TechCrunch, SemiAnalysis."""


# ─────────── сгъвката „Рутината" (M20-FIX2) — статична, детерминистична ──────────
_ROUTINE_FOLD = """
  <details>
    <summary>Рутината — как се обновява уредът и как се търсят новини</summary>

    <p style="font-weight:700;margin:6px 0 2px;font-size:13.5px">Блок 1 · Каденца — кой компонент, откъде, колко често</p>
    <table><thead><tr><th>компонент</th><th>източник</th><th>честота</th><th>скрипт</th></tr></thead>
      <tbody>
        <tr><td>корпоративна реторика</td><td>SEC EDGAR (8-K език)</td><td>при ново подаване</td><td class='src'>rhetoric_v2.py</td></tr>
        <tr><td>обещания/резултати</td><td>SEC EDGAR</td><td>при ново подаване</td><td class='src'>promise_delivery.py</td></tr>
        <tr><td>нови емисии (IPO)</td><td>EDGAR FTS + form.idx</td><td>тримесечно</td><td class='src'>froth.py</td></tr>
        <tr><td>оценъчен множител</td><td>price-archive + XBRL facts</td><td>седмично</td><td class='src'>multiple_v2.py</td></tr>
        <tr><td>фундамент (приходи, марж)</td><td>SEC XBRL, point-in-time</td><td>тримесечно, ~45-дневен SEC lag</td><td class='src'>collect_xbrl.py → gap.py</td></tr>
        <tr><td>композит G + зона</td><td>горните</td><td>седмично</td><td class='src'>gap.py → zones.py</td></tr>
        <tr><td>това лице</td><td>всичко по-горе</td><td>седмично</td><td class='src'>render_onepager_html.py</td></tr>
      </tbody></table>

    <p style="font-weight:700;margin:14px 0 2px;font-size:13.5px">Блок 2 · Седмичната рутина (командите се пускат от корена на репото)</p>
    <ol class="routine-steps">
      <li>Обнови фундамента (тримесечно, при ново SEC подаване) — дърпа новите XBRL факти (point-in-time):<br>
        <code>python src\\v2\\collect_xbrl.py</code></li>
      <li>Обнови четирите компонента на еуфорията — реторика, обещания/резултати, нови емисии (IPO, тримесечно), оценъчен множител (седмично):<br>
        <code>python src\\v2\\rhetoric_v2.py</code><br>
        <code>python src\\v2\\promise_delivery.py</code><br>
        <code>python src\\v2\\froth.py</code><br>
        <code>python src\\v2\\multiple_v2.py</code></li>
      <li>Сглоби композитите — Еуфория E, разминаването G + фундамент, и зоната:<br>
        <code>python src\\v2\\euphoria.py</code><br>
        <code>python src\\v2\\gap.py</code><br>
        <code>python src\\v2\\zones.py</code></li>
      <li>Регенерирай лицето — записва <code>docs\\index.html</code> (по избор подай as-of дата: <code>python src\\v2\\render_onepager_html.py 2026-07-17</code>):<br>
        <code>python src\\v2\\render_onepager_html.py</code></li>
      <li>Отвори <code>docs\\index.html</code> и свери as-of датата в горния ред.</li>
    </ol>
    <p class="routine-note">CI е нарочно паузиран — събужда се с отделно решение СЛЕД одобрението на лицето; дотогава рутината е ръчна.</p>

    <p style="font-weight:700;margin:14px 0 2px;font-size:13.5px">Блок 3 · Новинарската рутина (пукнатините) + промптът за Perplexity</p>
    <p class="routine-note">Пукнатините T1–T13 са дискретни събития ИЗВЪН числото G; статусът им се сменя САМО от човек.
      Watcher-ите (t7, t9, t10) пишат само кандидати в <code>out\\</code>. Новинарските (T1–T6, T8, T10–T12) се търсят ръчно —
      с промпта долу, седмично. T9 нарочно липсва от промпта: той е машинно наблюдаван от <code>t9_froth.py</code>.
      T13 също не е новинарска — сверява се тримесечно от 10-Q таблиците (RPO концентрацията), при четенето на отчетите.
      Кредитният слой (T11–T13) има доказателствен анекс: <code>research/reconciliation-matrix-2026-07-22.md</code>.</p>
    <div class="copyrow">
      <button type="button" class="copybtn" data-copy="ppx-prompt">копирай</button>
      <span class="routine-note" style="margin:0">Perplexity промпт — вмъква се дословно.</span>
    </div>
    <pre id="ppx-prompt">{ppx}</pre>

    <p style="font-weight:700;margin:14px 0 2px;font-size:13.5px">Блок 4 · Какво правиш с намереното</p>
    <ol class="routine-steps">
      <li>Провери първоизточника (линка) — Perplexity само насочва, не решава.</li>
      <li>Ако е реално: редактирай <code>app/data/v2/tripwires.yaml</code> — <code>status: fired</code>,
        <code>fired_date</code> (датата на събитието/съобщението), <code>source</code> (издание + дата).</li>
      <li>Регенерирай лицето (командата от Блок 2) — картата се появява в журнала сама.</li>
      <li>Ако е гранично: остави статуса, запиши бележка в <code>source</code> полето ([Н] конвенцията).</li>
      <li>Никога не сменяй статус само по заглавие — уредът е наблюдение, не сигнал, но журналът му е доказателствен.</li>
    </ol>
  </details>
""".replace("{ppx}", esc(_PPX_PROMPT))


# ───────────── малкият JS: плаващи менюта + копи-бутон (self-contained) ─────────────
_SCRIPT = """<script>
(function(){
  function closeAll(except){
    var ps = document.querySelectorAll('.pop.open');
    for (var i=0;i<ps.length;i++){ if(ps[i]!==except){ ps[i].classList.remove('open'); } }
  }
  function toggle(p){
    var open = p.classList.contains('open');
    closeAll(p);
    if(open){ p.classList.remove('open'); } else { p.classList.add('open'); }
  }
  document.addEventListener('click', function(e){
    var t = e.target;
    if(t && t.closest){
      if(t.closest('.pop-card')){ e.stopPropagation(); return; }   // взаимодействие с картата — не затваряй
      var btn = t.closest('.copybtn');
      if(btn){ e.stopPropagation(); doCopy(btn); return; }
      var p = t.closest('.pop');
      if(p){ e.stopPropagation(); toggle(p); return; }
    }
    closeAll(null);
  });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape'){ closeAll(null); return; }
    var a = document.activeElement;
    if(a && a.classList && a.classList.contains('pop') && (e.key === 'Enter' || e.key === ' ')){
      e.preventDefault(); toggle(a);
    }
  });
  function selectNode(el){
    try{ var r=document.createRange(); r.selectNodeContents(el);
      var s=window.getSelection(); s.removeAllRanges(); s.addRange(r); }catch(err){}
  }
  function flash(btn, ok){
    var old = 'копирай';
    btn.textContent = ok ? 'копирано ✓' : 'маркирано — Ctrl+C';
    setTimeout(function(){ btn.textContent = old; }, 2200);
  }
  function doCopy(btn){
    var id = btn.getAttribute('data-copy');
    var pre = document.getElementById(id);
    if(!pre){ return; }
    var text = pre.textContent;
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(
        function(){ flash(btn, true); },
        function(){ selectNode(pre); var ok=false; try{ ok=document.execCommand('copy'); }catch(e){} flash(btn, ok); }
      );
    } else {
      selectNode(pre); var ok=false; try{ ok=document.execCommand('copy'); }catch(e){} flash(btn, ok);
    }
  }
})();
</script>"""


# ─────────────────────────── HTML шаблон ────────────────────────────
_PAGE = """<!doctype html>
<html lang="bg">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AI Hype Monitor v2 — каишката</title>
<style>
:root{{
  --bg:#f7f8fa; --panel:#ffffff; --ink:#16181d; --muted:#5b6472; --line:#e4e7ec;
  --accent:#4f46e5; --chipbg:#f1f3f7;
}}
@media (prefers-color-scheme: dark){{
  :root{{ --bg:#0f1115; --panel:#171a21; --ink:#e8eaed; --muted:#9aa4b2;
    --line:#262b34; --accent:#8b8cf0; --chipbg:#1e222b; }}
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;}}
.wrap{{max-width:820px;margin:0 auto;padding:28px 20px 64px;}}
a{{color:var(--accent);}}
a.ext{{text-decoration:underline dotted;text-underline-offset:2px;}}
.term{{border-bottom:1px dotted var(--muted);cursor:help;text-decoration:none;}}
.topbar{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
  justify-content:space-between;margin-bottom:18px;}}
.brand{{font-weight:700;letter-spacing:.2px;}}
.brand .v{{color:var(--accent);}}
.o4{{font-size:12px;font-weight:600;color:var(--muted);border:1px solid var(--line);
  border-radius:999px;padding:4px 11px;background:var(--panel);}}
.asof{{font-size:12.5px;color:var(--muted);margin:0 0 22px;}}
.verdict{{background:var(--panel);border:1px solid var(--line);border-left:5px solid var(--zc);
  border-radius:12px;padding:20px 22px;margin-bottom:20px;}}
.verdict h1{{font-size:20px;line-height:1.4;margin:0;font-weight:650;}}
.zonerow{{display:flex;align-items:center;gap:12px;margin:18px 0 8px;flex-wrap:wrap;}}
.zdot{{width:14px;height:14px;border-radius:50%;background:var(--zc);
  box-shadow:0 0 0 4px color-mix(in srgb,var(--zc) 22%,transparent);flex:none;}}
.zword{{font-size:18px;font-weight:700;color:var(--zc);}}
.zmean{{color:var(--muted);font-size:14px;}}
.zband{{position:relative;display:flex;height:30px;border-radius:7px;overflow:hidden;
  margin:6px 0 4px;border:1px solid var(--line);}}
.zseg{{display:flex;align-items:center;justify-content:center;}}
.zseg span{{font-size:10.5px;color:#fff;font-weight:600;text-shadow:0 1px 2px rgba(0,0,0,.35);
  white-space:nowrap;}}
.zmark{{position:absolute;top:-4px;bottom:-4px;width:3px;background:var(--ink);
  box-shadow:0 0 0 2px var(--panel);}}
.gline{{font-size:13px;color:var(--muted);margin:2px 0 0;}}
.posline{{font-size:14px;color:var(--muted);margin:8px 0 0;}}
.strip{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px;}}
.chip{{font-size:12.5px;font-weight:600;border:1.5px solid var(--muted);border-radius:999px;
  padding:4px 11px;background:var(--panel);display:inline-block;}}
.chip--calm{{color:var(--muted);border-color:var(--line);}}
/* ── плаващи менюта (M20-FIX1) ── */
.pop{{position:relative;text-decoration:none;cursor:help;outline:none;}}
.pop-anchor{{border-bottom:1px dotted var(--muted);}}
.pop:focus{{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px;}}
.pop-card{{position:absolute;left:0;top:calc(100% + 6px);z-index:60;display:none;
  min-width:200px;max-width:min(320px,82vw);background:var(--panel);color:var(--ink);
  border:1px solid var(--line);border-radius:9px;box-shadow:0 8px 26px rgba(0,0,0,.18);
  padding:10px 12px;text-align:left;white-space:normal;letter-spacing:normal;
  text-transform:none;
  font:400 12.5px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;}}
.pop:hover>.pop-card,.pop:focus>.pop-card,.pop:focus-within>.pop-card,
.pop.open>.pop-card{{display:block;}}
.pop-val{{display:block;font-weight:700;font-variant-numeric:tabular-nums;
  color:var(--ink);margin-bottom:2px;}}
.pop-desc{{display:block;color:var(--muted);}}
.pop-src{{display:block;color:var(--muted);margin-top:5px;font-size:11.5px;word-break:break-word;}}
.pop--chip{{display:inline-block;}}
.pop--chip .pop-anchor{{border-bottom:none;}}
.pop--band{{display:block;}}
.pop--zword .pop-anchor{{border-bottom-color:currentColor;}}
h2.sec{{font-size:15px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);
  margin:34px 0 6px;font-weight:700;}}
.lead{{color:var(--muted);font-size:14px;margin:0 0 14px;}}
.tw-card{{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:15px 17px;margin-bottom:12px;}}
.tw-card--recent{{border-color:var(--zc);}}
.tw-head{{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:7px;}}
.tw-id{{font-weight:800;color:var(--accent);font-size:14px;}}
.tw-name{{font-weight:650;}}
.tw-recent{{font-size:11px;font-weight:700;color:#fff;background:var(--accent);
  border-radius:999px;padding:2px 9px;}}
.tw-what{{margin:0 0 10px;font-size:14px;}}
.tw-when{{font-weight:700;}}
.tw-reads{{display:grid;gap:6px;}}
.tw-bear,.tw-bull{{margin:0;font-size:13.5px;color:var(--muted);}}
.tw-lab{{display:inline-block;font-size:11px;font-weight:800;text-transform:uppercase;
  letter-spacing:.4px;border-radius:5px;padding:1px 7px;margin-right:6px;color:#fff;}}
.tw-lab--bear{{background:#dc2626;}}
.tw-lab--bull{{background:#16a34a;}}
.armed{{list-style:none;padding:0;margin:6px 0 0;border-top:1px solid var(--line);}}
.armed-item{{display:flex;gap:10px;align-items:baseline;padding:8px 2px;
  border-bottom:1px solid var(--line);font-size:13px;}}
.armed-id{{font-weight:800;color:var(--muted);min-width:30px;}}
.armed-name{{flex:1;}}
.armed-src{{color:var(--muted);font-size:11.5px;max-width:44%;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}}
details{{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:6px 17px;margin-top:14px;}}
summary{{cursor:pointer;font-weight:700;padding:10px 0;font-size:14.5px;}}
details table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 16px;}}
details th,details td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);
  vertical-align:top;}}
details th{{color:var(--muted);font-weight:600;}}
td.num{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap;}}
td.src{{color:var(--muted);font-size:11.5px;word-break:break-all;}}
.formula{{font-size:14px;background:var(--chipbg);border-radius:8px;padding:11px 13px;
  margin:8px 0 14px;}}
.glossary dt{{font-weight:700;margin-top:9px;font-size:13.5px;}}
.glossary dd{{margin:2px 0 0;color:var(--muted);font-size:13px;}}
/* ── сгъвката „Рутината" (M20-FIX2) ── */
details pre{{background:var(--chipbg);border:1px solid var(--line);border-radius:8px;
  padding:12px 14px;white-space:pre-wrap;word-break:break-word;overflow-x:auto;margin:8px 0;
  font:12.5px/1.5 ui-monospace,"Cascadia Code",Consolas,"Courier New",monospace;}}
.copyrow{{display:flex;align-items:center;gap:10px;margin:10px 0 2px;flex-wrap:wrap;}}
.copybtn{{font:600 12px system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
  color:#fff;background:var(--accent);border:none;border-radius:7px;padding:6px 13px;
  cursor:pointer;}}
.copybtn:hover{{opacity:.9;}}
.routine-steps{{margin:6px 0 12px;padding-left:22px;font-size:13.5px;line-height:1.65;}}
.routine-steps li{{margin:6px 0;}}
.routine-steps code,.routine-note code{{background:var(--chipbg);border-radius:5px;
  padding:1px 6px;font:12px ui-monospace,Consolas,"Courier New",monospace;
  word-break:break-word;}}
.routine-note{{color:var(--muted);font-size:12.5px;margin:6px 0 2px;line-height:1.6;}}
footer{{margin-top:34px;color:var(--muted);font-size:12px;line-height:1.7;
  border-top:1px solid var(--line);padding-top:16px;}}
.retlink{{font-size:12px;}}
</style>
</head>
<body>
<div class="wrap" style="--zc:{zcolor}">

  <div class="topbar">
    <div class="brand">⚡ AI Hype Monitor <span class="v">v2</span> · барометърът на каишката</div>
    <span class="o4" title="Уредът описва състояние, не дава препоръка за покупка/продажба.">{o4}</span>
  </div>
  <p class="asof">Генерирано: <strong>{as_of}</strong> · данни до: <strong>{wk}</strong>
    (последна пълна G седмица; тримесечните компоненти стъпват със ~45-дневен SEC lag).</p>

  <!-- ИЗВОДЪТ ПЪРВО (канон §1.1) -->
  <div class="verdict">
    <h1>{conclusion}</h1>

    <div class="zonerow">
      <span class="zdot"></span>
      <span class="zword">{zone_word}</span>
      <span class="zmean">{zone_meaning}</span>
    </div>
    {zband}
    {posline}

    <div class="strip">{strip}</div>
  </div>

  <!-- ЖУРНАЛЪТ НА ПУКНАТИНИТЕ (канон §1.1 — разказ) -->
  <h2 class="sec">Журнал на пукнатините · {n_fired}/{n_total} задействани</h2>
  <p class="lead">Дискретни събития ИЗВЪН числото G (показват се до него, никога в него).
    Всяка пукнатина носи два прочита — мечи и бичи. Задействани към момента: {fired_ids}.</p>
  {cards}

  <details>
    <summary>Още {n_total} възможни пукнатини — заредени, но незадействани</summary>
    <ul class="armed">{armed}</ul>
    <p class="lead" style="margin-top:10px">Watcher-ите пишат само КАНДИДАТИ; статусът се сменя ръчно от човек.</p>
  </details>

  <!-- МЕХАНИКАТА В СГЪВКА (канон §1.1) -->
  <details>
    <summary>Как е сметнато — формула, компоненти и provenance</summary>

    <p class="gline">{term_gz} = <strong>{gz}</strong> ({gz_sig}) · {term_dg4} = {dg4} ({dg4_sig}),
      скоростен флаг: <strong>{vel}</strong> · G_raw = {graw} = E − F.</p>

    <div class="formula">
      <strong>G = E − F</strong> (еуфория минус фундамент), после
      <strong>{term_robust}</strong> спрямо ретроспективната G-история.<br>
      Зоните по G_z: Обърната ≤ −2σ · Провиснала −2..−1σ · <strong>Неутрална −1..+1σ</strong>
      · Разтегната +1..+2σ · Опъната напред ≥ +2σ (праговете a=1.0, b=2.0 са замразени/пре-регистрирани).
    </div>

    <p style="font-weight:700;margin:6px 0 2px;font-size:13.5px">Еуфория {term_e} — 4 гласа</p>
    <table><thead><tr><th>глас</th><th>z (точно)</th><th>σ</th></tr></thead>
      <tbody>{comp_rows}</tbody></table>
    <p style="color:var(--muted);font-size:13px;margin:0 0 14px">
      E = {E} · Фундамент {term_f} = {F} · пяна дял = {froth_share} ({froth_q}).</p>

    <p style="font-weight:700;margin:6px 0 2px;font-size:13.5px">Provenance — всяко число до съхранен вход</p>
    <table><thead><tr><th>metric</th><th>value</th><th>source</th><th>known_at</th></tr></thead>
      <tbody>{prov_rows}</tbody></table>

    <dl class="glossary">
      <dt>робастен z</dt><dd>Стандартизация чрез медиана и MAD — устойчива на извънредни стойности.</dd>
      <dt>known_at</dt><dd>Датата/тримесечието, към което входът е бил известен (point-in-time).</dd>
      <dt>скоростен флаг</dt><dd>Отбелязва бързо движение на G_z (dG₄); само сигнализира, не мести зоната.</dd>
      <dt>пяна по ръбовете</dt><dd>Делът на нови S-1 проспекти, споменаващи „artificial intelligence".</dd>
      <dt>градационна скала</dt><dd>Градациите в текста следват фиксирана z-скала: под 1σ — „в историческата норма"; 1–2σ — „над/под нормата"; 2–3σ — „съществено над/под нормата"; над 3σ — „исторически връх/дъно".</dd>
    </dl>
    <p style="color:var(--muted);font-size:12px;margin:2px 0 8px">
      Числата идват от детерминистичен код; пяна от EDGAR FTS; F от SEC XBRL (PIT); цени от price-archive.
      Няма прилагателни без числова основа — градациите следват фиксираната z-скала (речника).</p>
  </details>
{routine_fold}
  <footer>
    AI Hype Monitor v2 · измерва разминаването еуфория−фундамент в AI сектора ·
    изграден от <strong>Цветослав Цачев</strong>.<br>
    Информацията е само за аналитични цели и не представлява инвестиционен съвет.<br>
    <span class="retlink">Стар модел (v1, 0–100 score) е <strong>пенсиониран</strong> и заменен от този уред — една истина, едно лице.</span>
  </footer>

</div>
{script}
</body>
</html>
"""


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else AS_OF
    build(a)
