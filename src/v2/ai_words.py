"""
ai_words.py: AI думите в съобщенията за резултати, третата съставка на историята (ПРОЛЕТР9).
=============================================================================================
Решение на Ц. (26.11.2026, „Да, с пробата“): AI думите минават от ръчния корпус към пълнотекстовото
търсене на SEC, с проба дали серията мърда. Пробата мина мярката (27.11.2026) и Ц. реши „Само
думите“ (27.11.2026): серията влиза в стрелката на историята; Wikipedia остава проба.

Мери ШИРИНАТА, не гъстотата: в какъв дял от документите в 8-K, които приличат на съобщение за
резултати, стои „artificial intelligence“. По образа на froth.py (EDGAR full-text search, само
броят `total`, без да се теглят документите):

  числител:   8-K документи с „artificial intelligence“ И „three months ended“
  знаменател: 8-K документи с „three months ended“
  тримесечието е по датата на подаване (съобщенията за 2026Q3 се подават през 2026Q4).

EFTS брои документи (основният 8-K и всяко приложение поотделно) и спира на 10 000; при
„gte“ периодът се дели на месеци и после на половини, докато всеки брой е точен. За последното
тримесечие пробата тегли и първата страница от числителя, за да покаже какви документи брои
(`file_type`, `items`), без да ги пази.

Вика SEC: изисква SEC_USER_AGENT (src/v2/sec_ua.py). Кеш: app/data/v2/ai_words_cache/ (приключило
тримесечие се пита веднъж и се пази, какъвто е бил броят тогава). Изход: app/data/v2/ai_words.json.
Седмичният ход го пуска; ако последното приключило тримесечие вече е във файла, не вика SEC.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sec_ua import sec_headers  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "app" / "data" / "v2"
CACHE = V2 / "ai_words_cache"
OUT = V2 / "ai_words.json"
EFTS = "https://efts.sec.gov/LATEST/search-index?"
Q_NUM = '"artificial intelligence" "three months ended"'
Q_DEN = '"three months ended"'
CAP = 10000


def _get(url, tries=5):
    last = None
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=sec_headers()), timeout=60) as r:
                return r.read()
        except Exception as ex:  # 5xx при EDGAR са спорадични
            last = ex
            if a == tries - 1:
                raise
            time.sleep([5, 10, 15, 20][min(a, 3)])
    raise last


def efts(params):
    # НЕ dateRange=custom (HTTP 500, доказано във froth.py); само startdt/enddt
    d = json.loads(_get(EFTS + urllib.parse.urlencode(params)).decode())
    time.sleep(1.5)
    return d


def total(q, start: date, end: date):
    """Точен брой документи за периода; дели периода, докато EFTS не стигне тавана."""
    key = f"{'num' if q == Q_NUM else 'den'}_{start}_{end}.json"
    ck = CACHE / key
    if ck.exists():
        return json.loads(ck.read_text(encoding="utf-8"))["total"]
    d = efts({"q": q, "forms": "8-K", "startdt": start.isoformat(), "enddt": end.isoformat()})
    t = d["hits"]["total"]
    if t.get("relation") == "gte" or t["value"] >= CAP:
        if start == end:
            raise SystemExit(f"EFTS cap on a single day {start}: cannot split further")
        mid = start + (end - start) // 2
        n = total(q, start, mid) + total(q, mid + timedelta(days=1), end)
    else:
        n = t["value"]
    ck.write_text(json.dumps({"total": n}), encoding="utf-8")
    return n


def quarter_bounds(y, k):
    s = date(y, 3 * k - 2, 1)
    e = (date(y + (k == 4), 1 if k == 4 else 3 * k + 1, 1)) - timedelta(days=1)
    return s, e


def complete_quarters(first=(2023, 1)):
    t = date.today()
    y, k = t.year, (t.month - 1) // 3 + 1
    y, k = (y - 1, 4) if k == 1 else (y, k - 1)       # само приключилите
    out, (yy, kk) = [], first
    while (yy, kk) <= (y, k):
        out.append((yy, kk))
        yy, kk = (yy + 1, 1) if kk == 4 else (yy, kk + 1)
    return out


def sample(y, k):
    """Какво брои числителят: file_type и items на първите 100 документа (без да се пазят)."""
    s, e = quarter_bounds(y, k)
    d = efts({"q": Q_NUM, "forms": "8-K", "startdt": s.isoformat(), "enddt": e.isoformat()})
    ft, items = {}, {}
    for h in d["hits"]["hits"]:
        src = h.get("_source", {})
        f = src.get("file_type") or "?"
        ft[f] = ft.get(f, 0) + 1
        for it in src.get("items") or []:
            items[it] = items.get(it, 0) + 1
    return {"n": len(d["hits"]["hits"]), "file_type": dict(sorted(ft.items(), key=lambda x: -x[1])),
            "items": dict(sorted(items.items(), key=lambda x: -x[1])[:8])}


def main():
    last = complete_quarters()[-1]
    if OUT.exists():
        have = [r["filing_quarter"] for r in json.loads(OUT.read_text(encoding="utf-8"))["series"]]
        if have and have[-1] == f"{last[0]}Q{last[1]}":
            print(f"[ai_words] {have[-1]} already in {OUT.name}; no SEC call")
            return
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for y, k in complete_quarters():
        s, e = quarter_bounds(y, k)
        num, den = total(Q_NUM, s, e), total(Q_DEN, s, e)
        rows.append({"filing_quarter": f"{y}Q{k}", "ai_docs": num, "earnings_like_docs": den,
                     "share": round(num / den, 4) if den else None})
        print(f"  {y}Q{k}: {num} / {den}", flush=True)
    out = {
        "what": "AI думите в съобщенията за резултати (ширина); третата съставка на историята",
        "decided": "Ц., 27.11.2026: „Само думите“",
        "by": "ПРОЛЕТР9", "built": date.today().isoformat(),
        "method": {"numerator": Q_NUM, "denominator": Q_DEN, "forms": "8-K",
                   "unit": "документи в EFTS (основният 8-K и приложенията поотделно)",
                   "quarter": "по датата на подаване; съобщенията за тримесечие Q се подават през Q+1"},
        "source": "SEC EDGAR full-text search (efts.sec.gov/LATEST/search-index), само броят total",
        "sample_last_quarter": {"quarter": f"{last[0]}Q{last[1]}", **sample(*last)},
        "series": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[ai_words] {len(rows)} quarters -> {OUT}")


if __name__ == "__main__":
    main()
