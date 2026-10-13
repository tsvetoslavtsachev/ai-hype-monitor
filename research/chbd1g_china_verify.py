"""ЧБД1г, Р2: поправки и добавки на проверяващия към двата CSV на изследователя.

Чете china_ai_2026-10_chbd1g.csv и china_capex_2026-10_chbd1g.csv (папката на видеото), прилага
поправките от повторната проверка (13.10.2026) и добавя новите редове. Идемпотентен: добавените редове
се търсят по metric и не се дублират; поправките се прилагат по точно име на metric.

Пускане: python -I chbd1g_china_verify.py <папката на видеото>
Числата в новите редове са прочетени в тази сесия от:
  - openrouter.ai/rankings (браузър, 13.10.2026: Market Share с hover, LLM Leaderboard This Week, Benchmarks)
  - openrouter.ai/api/v1/models (13.10.2026 14:32 UTC), openrouter.ai/state-of-ai (12.2025)
  - официалните ценови страници (OpenAI, Google, MiniMax), SEC 6-K на Alibaba 24.02.2025, FRED DEXCHUS
  - stdaily.com (NIISDRC 34,2%), Синхуа (НАД), Yicai (WEF)
"""
import csv
import sys

FX_Q2_25, FX_Q2_26 = 7.2331, 6.8048
CN3_Q2_25, CN3_Q2_26 = 61583, 131852
US5_Q2_26 = 193.5  # описът, ред 232

OR = "https://openrouter.ai/rankings"
ORM = "https://openrouter.ai/api/v1/models"
SOA = "https://openrouter.ai/state-of-ai"
BABA_380 = "https://www.sec.gov/Archives/edgar/data/1577552/000110465925016348/tm257405d1_ex99-1.htm"


def r(metric, value, unit, as_of, source, url, status, note=""):
    return ["R2", metric, value, unit, as_of, source, url, status, note]


def new_ai_rows():
    rows = []
    # OpenRouter: абсолютните заявки по автор (легендата при hover), двете крайни седмици
    w1 = [("Google", 325), ("OpenAI", 138), ("Meta Llama", 70.1), ("DeepSeek", 67.9), ("Qwen", 65.2),
          ("SpaceXAI", 63.5), ("Mistral AI", 48.9), ("Anthropic", 40.1), ("Z.ai", 13.1), ("Others", 38.8)]
    w2 = [("DeepSeek", 1600), ("OpenAI", 1210), ("Google", 1160), ("Z.ai", 873), ("Qwen", 353),
          ("Anthropic", 252), ("Xiaomi", 191), ("Mistral AI", 131), ("Tencent", 112), ("Others", 632)]
    for wk, data in (("20.10.2025", w1), ("05.10.2026", w2)):
        for a, v in data:
            rows.append(r(f"OpenRouter: текстови заявки за седмицата от {wk}: {a}", v, "млн заявки", wk,
                          "OpenRouter Rankings, Market Share (легендата при hover)", OR, "В",
                          "заявки, не токени; препроверено в браузъра 13.10.2026"))
    cn1 = round(67.9 + 65.2 + 13.1, 1)
    cn2 = 1600 + 873 + 353 + 191 + 112
    rows.append(r("OpenRouter: заявки на поименните китайски автори, седмица от 20.10.2025", cn1, "млн заявки",
                  "20.10.2025", "изчисление", OR, "Х", "DeepSeek 67,9 + Qwen 65,2 + Z.ai 13,1"))
    rows.append(r("OpenRouter: заявки на поименните китайски автори, седмица от 05.10.2026", cn2, "млн заявки",
                  "05.10.2026", "изчисление", OR, "Х", "DeepSeek 1 600 + Z.ai 873 + Qwen 353 + Xiaomi 191 + Tencent 112"))
    rows.append(r("OpenRouter: ръст на заявките на китайските автори за година", round(cn2 / cn1, 1), "пъти",
                  "05.10.2026", "изчисление", OR, "Х", f"{cn2} / {cn1}"))

    # Benchmarks: места в целия списък (346 модела), без точките (те са само в графиката)
    ranks = [("DeepSeek V4.1 Flash (Max)", 28, "CN", "№1 по токени в OpenRouter"),
             ("DeepSeek V4 Pro 0813 (Max)", 36, "CN", ""),
             ("DeepSeek V4 Flash 0731 (Max)", 38, "CN", ""),
             ("MiMo-V2.6-Flash", 34, "CN", ""),
             ("Qwen3.8 2.4T A95B (отворените тегла на Qwen3.8 Max)", 25, "CN", ""),
             ("Hy3", 69, "CN", ""),
             ("Gemini 3.8 Flash (High)", 23, "US", ""),
             ("GPT-6 Luna (Max)", 33, "US", ""),
             ("GPT-5.6 Luna (Max)", 35, "US", ""),
             ("Nemotron 3 Ultra 550B A55B (Reasoning)", 86, "US", "")]
    for name, pos, org, extra in ranks:
        note = f"произход {org}; място от 346 в списъка на OpenRouter; котировка на OpenRouter, AA не е отворен"
        if extra:
            note += f"; {extra}"
        rows.append(r(f"Artificial Analysis Intelligence Index: {name}, място", pos, "място", "13.10.2026",
                      "OpenRouter Rankings, Benchmarks (търсачката на графиката)", OR, "В", note))
    rows.append(r("Artificial Analysis Intelligence Index: брой модели в списъка на OpenRouter", 346, "модела",
                  "13.10.2026", "OpenRouter Rankings, Benchmarks", OR, "В", "Step 5 Preview и Hy4 preview не са в списъка"))
    rows.append(r("Qwen3.8 Max (0902): общ брой параметри (MoE)", 2.4, "трлн параметъра", "13.10.2026",
                  "OpenRouter /api/v1/models, описание на qwen/qwen3.8-max-0902", ORM, "В",
                  "котировка на OpenRouter; отворената версия Qwen3.8 2.4T A95B е с 95 млрд активни параметъра"))

    # Цени: американският евтин клас (официални страници) и нова котировка на OpenRouter
    for model, pin, pout, url, note in (
            ("OpenAI GPT-6 Luna", 0.10, 0.50, "https://developers.openai.com/api/docs/pricing",
             "стандарт, кратък контекст (до 272k); на OpenRouter същото 0,1/0,5"),
            ("Google Gemini 3.8 Flash", 0.75, 3.75, "https://ai.google.dev/gemini-api/docs/pricing",
             "до 31.12.2026; от 01.01.2027 1,50/7,50; до 200k")):
        rows.append(r(f"Цена вход: {model}", pin, "$ за 1 млн токена", "13.10.2026", "официална ценова страница", url, "В", note))
        rows.append(r(f"Цена изход: {model}", pout, "$ за 1 млн токена", "13.10.2026", "официална ценова страница", url, "В", note))
        rows.append(r(f"Цена изход {model} / Claude Opus 5.5", round(pout / 20, 4), "съотношение", "13.10.2026",
                      "изчисление", url, "Х", f"{pout}/20"))
        rows.append(r(f"Цена изход {model} / GPT-6 Astra", round(pout / 50, 4), "съотношение", "13.10.2026",
                      "изчисление", url, "Х", f"{pout}/50"))
    rows.append(r("OpenRouter котировка вход/изход: deepseek/deepseek-v4.1-flash (повторно)", "0.0441/0.63",
                  "$ за 1 млн токена", "2026-10-13T14:32:16Z", "OpenRouter /api/v1/models", ORM, "В",
                  "в 14:05 UTC беше 0,0438/0,1752; котировката се мени в рамките на часа"))

    # Капекс: ръст в $, ByteDance като допускане, темпото на Alibaba спрямо обещанието
    usd25, usd26 = CN3_Q2_25 / FX_Q2_25, CN3_Q2_26 / FX_Q2_26
    rows.append(r("Капекс Alibaba+Tencent+Baidu, Q2 2026 г/г в $", round((usd26 / usd25 - 1) * 100, 1), "%", "Q2 2026",
                  "изчисление", "", "Х", f"({CN3_Q2_26}/{FX_Q2_26}) / ({CN3_Q2_25}/{FX_Q2_25}) - 1"))
    for lab, q_usd, src, formula in (
            ("FT 160 млрд юана", 160000 / 4 / FX_Q2_26 / 1000, "FT 23.12.2025", "(19,376 + 160/4/6,8048) / 193,5"),
            ("SCMP над 200 млрд юана", 200000 / 4 / FX_Q2_26 / 1000, "SCMP 09.05.2026", "(19,376 + 200/4/6,8048) / 193,5"),
            ("Bloomberg до $70 млрд", 70 / 4, "Bloomberg по LDS 27.05.2026", "(19,376 + 70/4) / 193,5")):
        val = round((CN3_Q2_26 / FX_Q2_26 / 1000 + q_usd) / US5_Q2_26 * 100, 1)
        rows.append(r(f"Капекс четирите китайски с ByteDance ({lab}) / петимата американски, Q2 2026", val, "%",
                      "Q2 2026", "изчисление", "", "Х",
                      f"{formula}; ByteDance е П ({src}), допускане: равномерно по тримесечия; американските: описът, ред 232"))
        rows.append(r(f"Капекс четирите китайски с ByteDance ({lab}), Q2 2026, в $", round(CN3_Q2_26 / FX_Q2_26 / 1000 + q_usd, 2),
                      "млрд $", "Q2 2026", "изчисление", "", "Х", f"{formula.split(' / ')[0]}; ByteDance е П ({src})"))
    lo = round(US5_Q2_26 / ((CN3_Q2_26 / FX_Q2_26 / 1000) + 17.5), 1)
    hi = round(US5_Q2_26 / (CN3_Q2_26 / FX_Q2_26 / 1000), 1)
    rows.append(r("Капекс: американските петима спрямо китайските, Q2 2026 (пъти), от-до", f"{lo}-{hi}", "пъти", "Q2 2026",
                  "изчисление", "", "Х", "193,5 / 36,88 (с ByteDance по Bloomberg) до 193,5 / 19,38 (тримата)"))
    rows.append(r("Капекс Alibaba+Tencent+Baidu, Q1 2026", 26887 + 31936 + 5916, "млн юана", "Q1 2026", "изчисление", "", "Х",
                  "26 887 + 31 936 + 5 916"))
    rows.append(r("Hugging Face google, само Gemma: сваляния от създаването", 581172259, "сваляния", "2026-10-13T14:32:16Z",
                  "Hugging Face API", "https://huggingface.co/api/models?author=google&expand[]=downloadsAllTime", "В",
                  "412 репа с 'gemma' в името; повторното теглене"))
    rows.append(r("OpenRouter топ 20: токени на китайските Flash варианти", 72.46, "трлн токена", "12.10.2026", "изчисление", OR, "Х",
                  "40,5 + 4,66 + 3,1 + 12,7 + 11,5"))
    rows.append(r("OpenRouter топ 20: токени на американския евтин клас", 18.12, "трлн токена", "12.10.2026", "изчисление", OR, "Х",
                  "7,17 + 7,11 + 2,03 + 1,81"))
    rows.append(r("OpenRouter топ 20: китайските Flash срещу американския евтин клас (пъти)", round(72.46 / 18.12, 1), "пъти",
                  "12.10.2026", "изчисление", OR, "Х", "72,46 / 18,12"))
    rows.append(r("Artificial Analysis Intelligence Index: Claude Opus 5.5 минус Qwen3.8 Max", round(57.6 - 53.4, 1), "точки",
                  "13.10.2026", "изчисление", OR, "Х", "57,6 - 53,4"))
    rows.append(r("Цена изход: челните американски срещу китайския евтин клас, от-до (пъти)", f"{round(20 / 1.20, 1)}-{round(50 / 0.50)}",
                  "пъти", "13.10.2026", "изчисление", "", "Х", "Opus 5.5 20 / 1,20 (DeepSeek V4.1 Flash пик, MiniMax M3) до GPT-6 Astra 50 / 0,50 (GLM-5.3-Flash)"))
    rows.append(r("Alibaba: изминало време от тригодишното обещание към 06.2026", round(5 / 12 * 100, 1), "%",
                  "Q2 2026", "изчисление", BABA_380, "Х", "5 от 12 тримесечия (04.2025-06.2026); срещу 51,0% изхарчени"))

    # a16z/OpenRouter State of AI: дял по държава на плащане (токени), 2025
    soa = [("САЩ", 47.17), ("Сингапур", 9.21), ("Германия", 7.51), ("Китай", 6.01), ("Южна Корея", 2.88),
           ("Северна Америка (континент)", 47.22), ("Азия (континент)", 28.61), ("Европа (континент)", 21.32)]
    for k, v in soa:
        rows.append(r(f"OpenRouter State of AI: дял от токените по място на плащане, {k}", v, "%", "12.2025",
                      "a16z/OpenRouter, State of AI (100 трлн токена)", SOA, "В",
                      "по billing location на акаунта, не по IP; САЩ+Канада (49,07) > Северна Америка (47,22): несъответствие в самия доклад"))
    rows.append(r("OpenRouter State of AI: дял от токените извън Китай (по място на плащане)", round(100 - 6.01, 2), "%",
                  "12.2025", "изчисление", SOA, "Х", "100 - 6,01"))

    # Официални китайски данни: допълнение
    rows.append(r("NIISDRC (към МИИТ): разпространение на AI в ключовите сценарии на преработващата промишленост, H1 2026",
                  34.2, "%", "20.09.2026", "доклад '制造业数智化转型能力水平(2026)', по Синхуа/科技日报 21.09.2026",
                  "https://www.stdaily.com/web/gdxw/2026-09/21/content_584767.html", "П",
                  "制造业人工智能重点场景应用普及率达34.2%; самият доклад не е отворен"))
    rows.append(r("Китай: дневна консумация на токени, март 2026, спрямо Google на ден", round(140 / (3200 / 30), 2),
                  "пъти", "24.03.2026 / 19.05.2026", "изчисление", "", "Х",
                  "140 / 106,7; различни мерки (извиквания в цял Китай срещу обработени при Google); П/Х"))
    return rows


AI_EDITS = {
    "OpenRouter: всички текстови заявки за седмица, 20.10.2025":
        {"value": 870.6, "note": "сбор на 10-те реда на легендата (Google 325, OpenAI 138, Meta Llama 70,1, DeepSeek 67,9, "
                                 "Qwen 65,2, SpaceXAI 63,5, Mistral 48,9, Anthropic 40,1, Z.ai 13,1, Others 38,8); 325/0,373 дава 871"},
    "OpenRouter: всички текстови заявки за седмица, 05.10.2026":
        {"value": 6.514, "note": "сбор на 10-те реда на легендата (DeepSeek 1 600, OpenAI 1 210, Google 1 160, Z.ai 873, Qwen 353, "
                                 "Anthropic 252, Xiaomi 191, Mistral 131, Tencent 112, Others 632 млн); 1,6/0,245 дава 6,53"},
    "OpenRouter: ръст на седмичните заявки за година": {"value": 7.48, "note": "6 514 / 870,6"},
    "Капекс тримата китайски / петимата американски (с Oracle), Q2 2026": {"note": "19.38/193.5 (описът, ред 232)"},
    "Капекс тримата китайски / четиримата американски (без Oracle), H1 2026": {"note": "28.64/294.8 (описът, ред 233)"},
    "Капекс ByteDance, 2025 план (Reuters, 23.01.2025)":
        {"note": "над 150 млрд юана; Reuters дава $20,64 млрд (П, по преразкази); The Standard (Reuters) е отворена: ByteDance не е "
                 "коментирал там; по преразкази на Reuters говорител е нарекъл числата 'incorrect' (П)"},
    "Капекс ByteDance, 2026 план (SCMP, 09.05.2026)":
        {"note": "над 200 млрд юана ($29,14 млрд по 6,8633, Х); SCMP 403, датата и числото през вторични (EqualOcean, TechNode)"},
    "Капекс ByteDance 2026, обсъждан таван (Bloomberg)":
        {"note": "разминава се със SCMP (200 млрд юана = $29,14 млрд по 6,8633, Х)"},
    "Alibaba: обещание за AI и облак за 3 години (от 24.02.2025)":
        {"url": BABA_380, "source": "Alibaba 6-K (ex99-1), 24.02.2025",
         "note": "'at least RMB380 billion (US$53 billion) over the next three years' (препроверено в 6-K); по Bloomberg (П, само в резюме "
                 "на търсене) Ву е казал, че сумата ще бъде надхвърлена"},
    "Alibaba: изхарчен капекс 04.2025-06.2026 спрямо 380 млрд":
        {"note": "(FY26 126063 + Q2'26 67678) / 380 000; броено от 04.2025 (началото на FY2026); целият капекс, не само AI"},
    "Google: токени на ден (приблизително)": {"metric": "Google: токени на ден (средно за 30-дневен месец)", "value": 106.7,
                                              "note": "3 200 / 30"},
    "МИИТ: дял на големите промишлени предприятия, ползващи AI":
        {"metric": "МИИТ: разпространение на AI технологиите в преработващите предприятия над прага за размер (规模以上)",
         "note": "规模以上制造业企业人工智能技术应用普及率超30%; същото 'над 30%' е казано и за края на 2025 (министър Ли Лечън, 03.2026; "
                 "П, само в резюме на търсене)"},
    "Финанси: China Merchants Bank, заменени човекочасове 2025":
        {"note": "7 780 души на пълен ден при 2 000 часа годишно (Х: 15,56 млн / 2 000; допускане)"},
    "Производство: фабрики 'фар' на WEF в Китай":
        {"note": "от над 220 в света; 16 нови в Китай, 'около 70%' от новата група (по Yicai, отворено 13.10.2026); weforum.org върна 403"},
    "Baidu: приходи от AI-powered Business, Q2 2026":
        {"note": "'continued to account for half of Baidu General Business revenue' (препроверено в 6-K); +25% г/г"},
}

PRICE_URL_NOTES = {
    "https://platform.openai.com/docs/pricing": "адресът пренасочва към developers.openai.com/api/docs/pricing (препроверено 13.10.2026)",
    "https://docs.claude.com/en/docs/about-claude/pricing": "адресът пренасочва към platform.claude.com/docs/en/about-claude/pricing (препроверено 13.10.2026)",
}

CAPEX_EDITS = {
    ("ByteDance", "2025 план (Reuters, 23.01.2025)"):
        {"note": "над 150 млрд юана (Reuters: $20,64 млрд, П); по преразкази на Reuters говорител на ByteDance нарече числата 'incorrect' (П)"},
    ("ByteDance", "2026 план (SCMP, 09.05.2026)"):
        {"note": "над 200 млрд юана; SCMP 403, датата и числото през вторични (EqualOcean, TechNode)"},
    ("Tencent", "Q2 2026"):
        {"note": "+176% г/г; капекс по дефиницията на Tencent (основното число); плащанията за капекс в паричния поток са 59,3 млрд"},
}


def apply_ai(path):
    rows = list(csv.reader(open(path, encoding="utf-8")))
    head, body = rows[0], rows[1:]
    idx = {c: i for i, c in enumerate(head)}
    seen_edit = set()
    for row in body:
        m = row[idx["metric"]]
        if m in AI_EDITS:
            for k, v in AI_EDITS[m].items():
                row[idx[k]] = str(v)
            seen_edit.add(m)
        if m.startswith(("Цена вход: MiniMax M3", "Цена изход: MiniMax M3", "Цена изход MiniMax M3")):
            row[idx["metric"]] = m.replace(" (котировка на OpenRouter)", "")
            if row[idx["status"]] == "В":
                row[idx["source"]] = "официална ценова страница"
                row[idx["url"]] = "https://platform.minimax.io/docs/pricing/overview"
                row[idx["note"]] = "Standard, до 512k вход, след 'Permanent 50% off'; на OpenRouter същото 0,3/1,2"
            else:
                row[idx["url"]] = "https://platform.minimax.io/docs/pricing/overview"
        if row[idx["url"]] in PRICE_URL_NOTES and row[idx["status"]] == "В" and "пренасочва" not in row[idx["note"]]:
            row[idx["note"]] = (row[idx["note"]] + "; " if row[idx["note"]] else "") + PRICE_URL_NOTES[row[idx["url"]]]
        if row[idx["url"]].startswith("https://platform.moonshot.ai") and "пренасочва" not in row[idx["note"]]:
            row[idx["note"]] = (row[idx["note"]] + "; " if row[idx["note"]] else "") + "адресът пренасочва към platform.kimi.ai"
    edited_metrics = {AI_EDITS[k].get("metric", k) for k in seen_edit}
    missing = [k for k in AI_EDITS if k not in seen_edit and AI_EDITS[k].get("metric", k) not in {r_[1] for r_ in body}]
    have = {row[idx["metric"]] for row in body}
    added = 0
    for nr in new_ai_rows():
        if nr[1] not in have:
            body.append([str(x) for x in nr])
            have.add(nr[1])
            added += 1
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows(body)
    return len(body), added, sorted(edited_metrics), missing


def apply_capex(path):
    rows = list(csv.reader(open(path, encoding="utf-8")))
    head, body = rows[0], rows[1:]
    idx = {c: i for i, c in enumerate(head)}
    n = 0
    for row in body:
        key = (row[idx["company"]], row[idx["period"]])
        if key in CAPEX_EDITS:
            for k, v in CAPEX_EDITS[key].items():
                row[idx[k]] = v
            n += 1
        if row[idx["fx_basis"]] in ("FRED DEXCHUS 2026H1", "FRED DEXCHUS LTM") and "дневната средна" not in row[idx["note"]]:
            daily = "6,8624" if row[idx["fx_basis"]].endswith("H1") else "6,9940"
            row[idx["note"]] = (row[idx["note"]] + "; " if row[idx["note"]] else "") + \
                f"курсът е средно от тримесечните средни; дневната средна е {daily}"
    have = {(row[idx["company"]], row[idx["period"]]) for row in body}
    q1 = 26887 + 31936 + 5916
    extra = ["R2", "Alibaba+Tencent+Baidu", "Q1 2026", str(q1), "6.9218", "FRED DEXCHUS 2026Q1",
             str(round(q1 / 6.9218 / 1000, 2)), "", "Х", "сбор (В по отчетите: 26 887 + 31 936 + 5 916)"]
    if ("Alibaba+Tencent+Baidu", "Q1 2026") not in have:
        body.append(extra)
        n += 1
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows(body)
    return len(body), n


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = sys.argv[1].rstrip("/\\")
    print("ai", apply_ai(f"{d}/china_ai_2026-10_chbd1g.csv"))
    print("capex", apply_capex(f"{d}/china_capex_2026-10_chbd1g.csv"))
