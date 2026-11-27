"""
probe_wiki.py: пробата за вниманието от Wikipedia (ПРОЛЕТР9, Фаза 3).
=====================================================================
Решение на Ц. (26.11.2026): вниманието от Wikipedia е проба по правилото на думите; влиза само с „да“.

Кошницата (приета от Ц. на 27.11.2026, без страници на компании, за да не повтаря цената):
Artificial intelligence, Generative artificial intelligence, Large language model, ChatGPT, OpenAI,
Artificial general intelligence. Английската Wikipedia, всички устройства, само хора (agent=user),
дневно от Wikimedia REST API, сбор по седмици, които свършват в петък (както пазарната стрелка).

Идентификацията на клиента идва от настройката WIKIMEDIA_USER_AGENT (Wikimedia иска име и контакт
в User-Agent); без нея скриптът спира. Пуска се от Ц. Изход: app/data/v2/probes/wiki.json.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "data" / "v2" / "probes" / "wiki.json"
ENV = "WIKIMEDIA_USER_AGENT"
BASKET = ["Artificial intelligence", "Generative artificial intelligence", "Large language model",
          "ChatGPT", "OpenAI", "Artificial general intelligence"]
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/{}/daily/{}/{}"
START = date(2023, 1, 1)


def user_agent():
    ua = (os.environ.get(ENV) or "").strip()
    if not ua:
        raise SystemExit(f"{ENV} is not set. Wikimedia asks for a client name and contact in the "
                         f"User-Agent header. Set the environment variable {ENV}.")
    return ua


def daily(title, start, end, ua):
    url = API.format(urllib.parse.quote(title.replace(" ", "_"), safe=""), start.strftime("%Y%m%d00"),
                     end.strftime("%Y%m%d00"))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=60) as r:
        items = json.loads(r.read().decode())["items"]
    time.sleep(0.2)
    return {f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}": i["views"] for i in items}


def friday_of(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7)      # седмицата свършва в петък


def main():
    ua = user_agent()
    end = date.today() - timedelta(days=1)
    last_fri = end - timedelta(days=(end.weekday() - 4) % 7)
    per = {t: daily(t, START, last_fri, ua) for t in BASKET}
    weeks = {}
    for t, dd in per.items():
        for d, v in dd.items():
            f = friday_of(date.fromisoformat(d)).isoformat()
            w = weeks.setdefault(f, {"week_end": f, "total": 0, "days": 0, **{x: 0 for x in BASKET}})
            w[t] += v
            w["total"] += v
    for t, dd in per.items():
        for d in dd:
            weeks[friday_of(date.fromisoformat(d)).isoformat()]["days"] += 1
    rows = [w for f, w in sorted(weeks.items()) if w["days"] == 7 * len(BASKET)]   # само пълните седмици
    out = {"probe": "вниманието от Wikipedia (кошница от шест страници)", "by": "ПРОЛЕТР9",
           "built": date.today().isoformat(), "basket": BASKET,
           "source": "Wikimedia REST API pageviews, en.wikipedia.org, all-access, agent=user, дневно",
           "week": "седмица, която свършва в петък; само седмици с всичките 7 дни за всичките 6 страници",
           "series": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[probe_wiki] {len(rows)} weeks -> {OUT}")


if __name__ == "__main__":
    main()
