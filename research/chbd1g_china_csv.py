"""ЧБД1г Р2: сглобява CSV изходите за Китай (употреба, цени, капекс, официални данни, примери).

Употреба:
    python -I chbd1g_china_csv.py <dir с hf_orgs.json и or_prices.json> <папка на видеото>

Входове:
  - hf_orgs.json, or_prices.json: от chbd1g_china_models.py (Hugging Face API и OpenRouter /api/v1/models);
  - ръчно вписаните числа по-долу: всяко с източник, URL, дата и статус (В/П), прочетени на 13.10.2026
    (SEC EDGAR 6-K/20-F на Alibaba и Baidu, отчетите на Tencent, официалните ценови страници, openrouter.ai/rankings,
    gov.cn, Синхуа, CNNIC, CAICT, прес за ByteDance);
  - курсът CNY/USD: FRED DEXCHUS през api.stlouisfed.org (средногодишен/тримесечен, тегленето 13.10.2026).
Изходи: china_ai_2026-10_chbd1g.csv и china_capex_2026-10_chbd1g.csv (UTF-8, разделител запетая).
Печата производните числа (Х) за черновата.
"""
import csv
import json
import sys

R = "R2"
TODAY = "13.10.2026"

# --- курсове CNY за 1 USD (FRED DEXCHUS, В, теглено 13.10.2026) ---
FX = {"2024": 7.1957, "2025": 7.1875, "2025Q2": 7.2331, "2026Q1": 6.9218, "2026Q2": 6.8048, "2026-06-30": 6.7851}
FX_URL = "https://api.stlouisfed.org/fred/series/observations?series_id=DEXCHUS"
FX["2026H1"] = round((FX["2026Q1"] + FX["2026Q2"]) / 2, 4)
FX["2025Q3"], FX["2025Q4"] = 7.1570, 7.0889
FX["LTM"] = round((FX["2025Q3"] + FX["2025Q4"] + FX["2026Q1"] + FX["2026Q2"]) / 4, 4)

SEC = "https://www.sec.gov/Archives/edgar/data/"
U = {
    "baba_20f": SEC + "1577552/000119312526231755/baba-20260331.htm",
    "baba_q2_26": SEC + "1577552/000110465926099220/tm2623667d1_ex99-1.htm",
    "baba_q1_26": SEC + "1577552/000110465926060224/tm2614494d1_ex99-1.htm",
    "baba_q1_25": SEC + "1577552/000110465925049400/tm2515233d1_ex99-1.htm",
    "baba_q1_24": SEC + "1577552/000110465924061145/tm2414429d1_ex99-1.htm",
    "baba_380": "https://www.alibabagroup.com/en-US/document-1830678592242057216",
    "bidu_cf": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001329099.json",
    "bidu_q4_25": SEC + "1329099/000119312526076505/d117608dex991.htm",
    "bidu_q1_26": SEC + "1329099/000119312526228123/d156481dex991.htm",
    "bidu_q2_26": SEC + "1329099/000119312526355431/d112854dex991.htm",
    "tc_fy25": "https://static.www.tencent.com/uploads/2026/03/18/e6a646796d0d869acc76271c9ee1a6a5.pdf",
    "tc_q2_26": "https://www.tencent.com/wp-content/uploads/2026/08/Tencent-Announces-2026-Second-Quarter-Results.pdf",
    "bd_2026_scmp": "https://scmp.com/tech/article/3352906/bytedance-raises-2026-capex-least-25-amid-ai-boom-rising-memory-costs-sources-say",
    "bd_2026_ft": "https://www.thestandard.com.hk/innovation/article/319982/ByteDance-plans-to-spend-160-b-yuan-towards-AI-infrastructure-in-2026-FT-reports",
    "bd_2026_bbg": "https://letsdatascience.com/news/bytedance-weighs-up-to-70b-in-ai-capex-6388b905",
    "bd_2025_reuters": "https://www.thestandard.com.hk/finance/article/225864/ByteDance-plans-150-billion-yuan-capex-in-2025-mostly-on-AI",
    "or_rank": "https://openrouter.ai/rankings",
    "or_models": "https://openrouter.ai/api/v1/models",
    "hf": "https://huggingface.co/api/models?author=<org>&expand[]=downloads&expand[]=downloadsAllTime",
    "ds": "https://api-docs.deepseek.com/quick_start/pricing",
    "kimi": "https://platform.moonshot.ai/docs/pricing/chat",
    "zai": "https://docs.z.ai/guides/overview/pricing",
    "qwen": "https://www.alibabacloud.com/help/en/model-studio/model-pricing",
    "oai": "https://platform.openai.com/docs/pricing",
    "ant": "https://docs.claude.com/en/docs/about-claude/pricing",
    "gem": "https://ai.google.dev/gemini-api/docs/pricing",
    "govcn": "https://www.gov.cn/zhengce/content/202508/content_7037861.htm",
    "nda": "https://www.news.cn/tech/20260324/050774b26bc54f429fce2d21e284949a/c.html",
    "miit": "https://www.news.cn/info/20260720/3f1a4b956f5941cc919139c8a17c1254/c.html",
    "cnnic": "https://www.ncsti.gov.cn/kjdt/kjrd/202609/t20260930_257515.html",
    "caict": "https://cn.chinadaily.com.cn/a/202608/03/WS6a709e67a310d709c2fc13ec.html",
    "google_io": "https://blog.google/innovation-and-ai/sundar-pichai-io-2026/",
    "banks": "https://www.mrjjxw.com/articles/2026-04-02/4323057.html",
    "futian": "https://m.bjnews.com.cn/detail/1739874392129169.html",
    "wef_yicai": "https://www2.yicaiglobal.com/news/china-has-most-lighthouse-factories-globally",
}

rows = []


def add(metric, value, unit, as_of, source, url, status, note=""):
    rows.append({"r": R, "metric": metric, "value": value, "unit": unit, "as_of": as_of, "source": source,
                 "url": url, "status": status, "note": note})


def r1(x):
    return round(x, 1)


def main(indir, outdir):
    hf = json.load(open(f"{indir}/hf_orgs.json", encoding="utf-8"))
    orp = json.load(open(f"{indir}/or_prices.json", encoding="utf-8"))

    # ===== (а) OpenRouter: дял на заявките по автор (Market Share, %), В като котировка на страницата =====
    weeks = {
        "20.10.2025": {"Google": 37.3, "OpenAI": 15.9, "Meta Llama": 8.0, "DeepSeek": 7.8, "Qwen": 7.5,
                       "SpaceXAI": 7.3, "Mistral AI": 5.6, "Anthropic": 4.6, "Others": 4.5, "Z.ai": 1.5},
        "06.04.2026": {"Google": 30.6, "OpenAI": 17.9, "DeepSeek": 9.5, "Others": 8.7, "Qwen": 7.7,
                       "Meta Llama": 6.9, "Anthropic": 5.0, "SpaceXAI": 4.9, "Z.ai": 4.5, "Mistral AI": 4.3},
        "06.07.2026": {"Google": 27.0, "DeepSeek": 20.2, "OpenAI": 16.6, "Others": 11.5, "Qwen": 5.2,
                       "Anthropic": 5.1, "Mistral AI": 4.3, "Meta Llama": 3.7, "Tencent": 3.2, "Xiaomi": 3.2},
        "05.10.2026": {"DeepSeek": 24.5, "OpenAI": 18.6, "Google": 17.8, "Z.ai": 13.4, "Others": 9.7,
                       "Qwen": 5.4, "Anthropic": 3.9, "Xiaomi": 2.9, "Mistral AI": 2.0, "Tencent": 1.7},
    }
    CN = {"DeepSeek", "Qwen", "Z.ai", "Xiaomi", "Tencent"}
    US = {"Google", "OpenAI", "Anthropic", "Meta Llama", "SpaceXAI"}
    shares = {}
    for wk, d in weeks.items():
        for a, v in d.items():
            add(f"OpenRouter дял от текстовите заявки, седмица от {wk}: {a}", v, "%", wk,
                "OpenRouter Rankings, Market Share (Percentage)", U["or_rank"], "В",
                "заявки, не токени; четено в браузъра 13.10.2026 (hover върху седмицата)")
        cn = r1(sum(v for a, v in d.items() if a in CN))
        us = r1(sum(v for a, v in d.items() if a in US))
        shares[wk] = (cn, us)
        add(f"OpenRouter: китайски автори (поименни), седмица от {wk}", cn, "%", wk, "изчисление", U["or_rank"], "Х",
            "сбор на поименните китайски автори (" + "+".join(a for a in d if a in CN) + "); долна граница, част от Others са китайски (Moonshot, MiniMax, StepFun)")
        add(f"OpenRouter: американски автори (поименни), седмица от {wk}", us, "%", wk, "изчисление", U["or_rank"], "Х",
            "сбор " + "+".join(a for a in d if a in US))
    # общ брой заявки за седмица (Х): автор/дял
    tot_25 = 325e6 / 0.373
    tot_26 = 1.6e9 / 0.245
    add("OpenRouter: Google, заявки в седмицата от 20.10.2025", 325, "млн заявки", "20.10.2025", "OpenRouter Rankings", U["or_rank"], "В")
    add("OpenRouter: DeepSeek, заявки в седмицата от 05.10.2026", 1.6, "млрд заявки", "05.10.2026", "OpenRouter Rankings", U["or_rank"], "В")
    add("OpenRouter: всички текстови заявки за седмица, 20.10.2025", round(tot_25 / 1e6), "млн заявки", "20.10.2025", "изчисление", U["or_rank"], "Х", "325 млн / 0,373")
    add("OpenRouter: всички текстови заявки за седмица, 05.10.2026", round(tot_26 / 1e9, 2), "млрд заявки", "05.10.2026", "изчисление", U["or_rank"], "Х", "1,6 млрд / 0,245 (1,6 е закръглено на страницата)")
    add("OpenRouter: ръст на седмичните заявки за година", round(tot_26 / tot_25, 1), "пъти", "05.10.2026", "изчисление", U["or_rank"], "Х", "(1,6/0,245)/(0,325/0,373)")

    # Топ 20 модела по токени, седмицата до 12.10.2026 (В)
    top20 = [("DeepSeek V4.1 Flash", "deepseek", 40.5, "CN"), ("GLM 5.3 Flash", "z-ai", 12.7, "CN"),
             ("Step 5 Preview", "stepfun", 12.1, "CN"), ("MiMo-V2.6-Flash", "xiaomi", 11.5, "CN"),
             ("Hy4 preview", "tencent", 8.31, "CN"), ("Nemotron 3 Ultra (free)", "nvidia", 7.17, "US"),
             ("GPT-6 Luna", "openai", 7.11, "US"), ("Claude Opus 5.5", "anthropic", 5.35, "US"),
             ("DeepSeek V4 Flash 0731", "deepseek", 4.66, "CN"), ("GLM 5.3", "z-ai", 3.96, "CN"),
             ("Jev 1.13", "typesafe", 3.31, "?"), ("DeepSeek V4 Flash 0423", "deepseek", 3.1, "CN"),
             ("Hy3", "tencent", 2.78, "CN"), ("Claude Sonnet 5.5", "anthropic", 2.65, "US"),
             ("Muse Spark 1.3 Contributor", "meta", 2.53, "US"), ("Kimi K3", "moonshotai", 2.3, "CN"),
             ("GPT-6.1 Sol", "openai", 2.23, "US"), ("Gemini 3.8 Flash", "google", 2.03, "US"),
             ("GPT-5.6 Luna", "openai", 1.81, "US"), ("GLM 5.2", "z-ai", 1.53, "CN")]
    for i, (m, a, t, reg) in enumerate(top20, 1):
        add(f"OpenRouter топ 20 по токени (седмица), #{i}: {m} ({a})", t, "трлн токена", "12.10.2026",
            "OpenRouter Rankings, LLM Leaderboard This Week", U["or_rank"], "В", f"произход {reg}")
    s_all = sum(x[2] for x in top20)
    s_cn = sum(x[2] for x in top20 if x[3] == "CN")
    s_us = sum(x[2] for x in top20 if x[3] == "US")
    s_flash_cn = sum(x[2] for x in top20 if x[3] == "CN" and "Flash" in x[0])
    s_top10 = sum(x[2] for x in top20[:10])
    s_top10_cn = sum(x[2] for x in top20[:10] if x[3] == "CN")
    add("OpenRouter топ 20: токени общо", round(s_all, 2), "трлн токена", "12.10.2026", "изчисление", U["or_rank"], "Х", "сбор на 20-те реда")
    add("OpenRouter топ 20: дял на китайските модели в токените", r1(s_cn / s_all * 100), "%", "12.10.2026", "изчисление", U["or_rank"], "Х", f"{round(s_cn,2)}/{round(s_all,2)}; 11 китайски модела")
    add("OpenRouter топ 20: дял на американските модели в токените", r1(s_us / s_all * 100), "%", "12.10.2026", "изчисление", U["or_rank"], "Х", f"{round(s_us,2)}/{round(s_all,2)}; 8 модела")
    add("OpenRouter топ 20: дял на Flash вариантите в китайските токени", r1(s_flash_cn / s_cn * 100), "%", "12.10.2026", "изчисление", U["or_rank"], "Х", f"{round(s_flash_cn,2)}/{round(s_cn,2)} (DeepSeek V4.1/V4 Flash, GLM 5.3 Flash, MiMo Flash)")
    cheap_us = ("Nemotron 3 Ultra (free)", "GPT-6 Luna", "Gemini 3.8 Flash", "GPT-5.6 Luna")
    s_cheap_us = sum(x[2] for x in top20 if x[0] in cheap_us)
    add("OpenRouter топ 20: дял на евтиния клас (Luna, Flash, безплатни) в американските токени", r1(s_cheap_us / s_us * 100), "%", "12.10.2026", "изчисление", U["or_rank"], "Х",
        f"{round(s_cheap_us,2)}/{round(s_us,2)} (Nemotron 3 Ultra free, GPT-6 Luna, Gemini 3.8 Flash, GPT-5.6 Luna)")
    add("OpenRouter топ 10: дял на китайските модели в токените", r1(s_top10_cn / s_top10 * 100), "%", "12.10.2026", "изчисление", U["or_rank"], "Х", f"{round(s_top10_cn,2)}/{round(s_top10,2)}")

    # Бенчмарк: Artificial Analysis Intelligence Index, както е показан на OpenRouter (В като котировка)
    aa = [("Claude Opus 5.5 (Max)", 57.6, "US"), ("Claude Sonnet 5.5 (Max)", 56.0, "US"), ("Claude Fable 5.1 (Max)", 53.4, "US"),
          ("Qwen3.8 Max", 53.4, "CN"), ("GPT-6 Astra (Max)", 52.7, "US"), ("GPT-6.1 Sol (Max)", 51.8, "US"),
          ("MiMo-V2.6-Pro", 46.3, "CN"), ("Qwen3.8 Max (0902)", 45.4, "CN"), ("GLM-5.3 (Max)", 44.8, "CN"),
          ("Kimi K3 (Max)", 43.6, "CN"), ("GLM-5.3-Flash", 41.8, "CN")]
    rank = {"Claude Opus 5.5 (Max)": 1, "Claude Sonnet 5.5 (Max)": 2, "Claude Fable 5.1 (Max)": 3, "Qwen3.8 Max": 4,
            "GPT-6 Astra (Max)": 5, "GPT-6.1 Sol (Max)": 6, "MiMo-V2.6-Pro": 13, "Qwen3.8 Max (0902)": 14,
            "GLM-5.3 (Max)": 15, "Kimi K3 (Max)": 17, "GLM-5.3-Flash": 20}
    for m, v, reg in aa:
        add(f"Artificial Analysis Intelligence Index: {m} (място {rank[m]})", v, "точки", TODAY,
            "OpenRouter Rankings, Benchmarks (по Artificial Analysis)", U["or_rank"], "В", f"произход {reg}; котировка на OpenRouter, AA не е отворен отделно")

    # ===== (б) Hugging Face сваляния =====
    pulled = hf["pulled_utc"]
    o = hf["orgs"]
    for org, v in o.items():
        if v.get("n_models"):
            add(f"Hugging Face {org}: сваляния за последните 30 дни (всички модели на организацията)", v["downloads_30d"], "сваляния", pulled,
                "Hugging Face API", U["hf"].replace("<org>", org), "В", f"{v['region']}; {v['n_models']} модела; топ: {v['top_model']} ({v['top_model_downloads_30d']})")
            add(f"Hugging Face {org}: сваляния от създаването", v["downloads_all_time"], "сваляния", pulled,
                "Hugging Face API", U["hf"].replace("<org>", org), "В", v["region"])
    g, oa = o["google"], o["openai"]
    add("Hugging Face google, само Gemma: сваляния 30 дни", g["gemma_downloads_30d"], "сваляния", pulled, "Hugging Face API", U["hf"].replace("<org>", "google"), "В", f"{g['gemma_n_models']} репа с 'gemma' в името")
    add("Hugging Face openai, само gpt-oss: сваляния 30 дни", oa["gpt_oss_downloads_30d"], "сваляния", pulled, "Hugging Face API", U["hf"].replace("<org>", "openai"), "В", "репа с 'gpt-oss' в името")
    cn_llm = sum(o[k]["downloads_30d"] for k in ("Qwen", "deepseek-ai", "moonshotai", "zai-org", "MiniMaxAI"))
    west_llm = o["meta-llama"]["downloads_30d"] + g["gemma_downloads_30d"] + o["mistralai"]["downloads_30d"] + oa["gpt_oss_downloads_30d"]
    add("Hugging Face: китайските пет (Qwen, DeepSeek, Moonshot, Z.ai, MiniMax), сваляния 30 дни", cn_llm, "сваляния", pulled, "изчисление", U["hf"], "Х", "сбор")
    add("Hugging Face: западните четири семейства (Llama, Gemma, Mistral, gpt-oss), сваляния 30 дни", west_llm, "сваляния", pulled, "изчисление", U["hf"], "Х", "сбор")
    add("Hugging Face: дял на китайските в сбора от двете групи (30 дни)", r1(cn_llm / (cn_llm + west_llm) * 100), "%", pulled, "изчисление", U["hf"], "Х",
        "по света (HF не дава държава); само репата на самите организации, без квантовани копия от трети страни")
    cn_org = sum(v.get("downloads_30d", 0) for v in o.values() if v.get("region") == "CN")
    we_org = sum(v.get("downloads_30d", 0) for v in o.values() if v.get("region") in ("US", "EU"))
    add("Hugging Face: дял на 9-те китайски организации срещу 4-те западни (meta-llama, google, mistralai, openai), всички модели, 30 дни",
        r1(cn_org / (cn_org + we_org) * 100), "%", pulled, "изчисление", U["hf"], "Х",
        f"{cn_org}/({cn_org}+{we_org}); google и openai включват и стари не-LLM модели (BERT, ELECTRA, CLIP, Whisper)")
    add("Hugging Face: Qwen срещу Llama, сваляния от създаването (пъти)", round(o["Qwen"]["downloads_all_time"] / o["meta-llama"]["downloads_all_time"], 1), "пъти", pulled, "изчисление", U["hf"], "Х", "Qwen/meta-llama, all time")
    add("Hugging Face: Qwen срещу Llama, сваляния 30 дни (пъти)", round(o["Qwen"]["downloads_30d"] / o["meta-llama"]["downloads_30d"], 1), "пъти", pulled, "изчисление", U["hf"], "Х", "Qwen/meta-llama")
    for org in ("Qwen", "meta-llama", "mistralai"):
        b = o[org]["downloads_30d_by_size"]
        t = sum(b.values())
        add(f"Hugging Face {org}: дял на моделите до 10 млрд параметъра в свалянията (30 дни)", r1(b.get("до 10 млрд", 0) / t * 100), "%", pulled,
            "изчисление по името на модела", U["hf"].replace("<org>", org), "Х", "размерът е взет от името (напр. 0.6B, 7B, 30B-A3B -> 30); репа без размер в името са отделна група")

    # ===== (в) цени: официални страници (В), $ за 1 млн токена =====
    prices = [
        ("OpenAI GPT-6 Astra (челен)", 10.0, 50.0, U["oai"], "В", "стандарт, кратък контекст (до 272k); openai.com/api/pricing върна 403, четено от platform.openai.com/docs/pricing"),
        ("OpenAI GPT-6.1 Sol", 2.0, 10.0, U["oai"], "В", "стандарт, кратък контекст"),
        ("Anthropic Claude Fable 5.1", 10.0, 50.0, U["ant"], "В", "базова цена"),
        ("Anthropic Claude Opus 5.5", 4.0, 20.0, U["ant"], "В", "базова цена"),
        ("Anthropic Claude Sonnet 5.5", 2.0, 10.0, U["ant"], "В", "базова цена"),
        ("Google Gemini 3.1 Pro Preview", 2.0, 12.0, U["gem"], "В", "до 200k токена; над 200k: 4/18"),
        ("DeepSeek V4 Pro (пик)", 1.32, 3.96, U["ds"], "В", "cache miss; пикови часове 01-04 и 06-10 UTC в делник"),
        ("DeepSeek V4 Pro (извън пика)", 0.66, 1.98, U["ds"], "В", "половината от пиковата цена"),
        ("DeepSeek Flash (V4.1) (пик)", 0.30, 1.20, U["ds"], "В", "cache miss"),
        ("DeepSeek Flash (V4.1) (извън пика)", 0.15, 0.60, U["ds"], "В", ""),
        ("Alibaba Qwen3.8 Max (International)", 2.0, 6.0, U["qwen"], "В", "до 1 млн токена; China (Beijing)/Global: 1,65/4,951"),
        ("Moonshot Kimi K3", 3.0, 15.0, U["kimi"], "В", "cache write 5 мин 3,00; cached input 0,30"),
        ("Z.ai GLM-5.3", 1.4, 4.4, U["zai"], "В", "същата цена като GLM-5.2"),
        ("Z.ai GLM-5.3-Flash", 0.15, 0.50, U["zai"], "В", ""),
    ]
    mm = orp["prices"].get("minimax/minimax-m3")
    prices.append(("MiniMax M3 (котировка на OpenRouter)", mm["in_usd_per_m"], mm["out_usd_per_m"], U["or_models"], "В",
                   "официалната страница на MiniMax не е отворена; котировка на OpenRouter"))
    for m, i, out, url, st, note in prices:
        add(f"Цена вход: {m}", i, "$ за 1 млн токена", TODAY, "официална ценова страница" if "OpenRouter" not in m else "OpenRouter /api/v1/models", url, st, note)
        add(f"Цена изход: {m}", out, "$ за 1 млн токена", TODAY, "официална ценова страница" if "OpenRouter" not in m else "OpenRouter /api/v1/models", url, st, note)
        add(f"Цена изход {m} / Claude Opus 5.5", round(out / 20.0, 3), "съотношение", TODAY, "изчисление", url, "Х", f"{out}/20")
        add(f"Цена изход {m} / GPT-6 Astra", round(out / 50.0, 3), "съотношение", TODAY, "изчисление", url, "Х", f"{out}/50")
    # котировки на OpenRouter за същите китайски модели (за разминаванията)
    for k in ("moonshotai/kimi-k3", "z-ai/glm-5.3", "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-pro-0813", "qwen/qwen3.8-max-0902"):
        p = orp["prices"][k]
        add(f"OpenRouter котировка вход/изход: {k}", f"{p['in_usd_per_m']}/{p['out_usd_per_m']}", "$ за 1 млн токена", orp["pulled_utc"],
            "OpenRouter /api/v1/models", U["or_models"], "В", "цена на базовия доставчик в OpenRouter; може да е трета страна, не лабораторията")

    # ===== (г) капекс: млн юана =====
    capex_rows = []

    def cap(company, period, rmb, url, st, note, fx_key):
        usd = rmb / FX[fx_key] / 1000 if rmb is not None else None
        capex_rows.append({"r": R, "company": company, "period": period, "capex_rmb_mn": rmb,
                           "fx_cny_per_usd": FX[fx_key], "fx_basis": f"FRED DEXCHUS {fx_key}",
                           "capex_usd_bn": round(usd, 2) if usd is not None else "", "source": url, "status": st, "note": note})
        add(f"Капекс {company}, {period}", rmb, "млн юана", period, "отчет" if st == "В" else "изчисление", url, st, note)
        if usd is not None:
            add(f"Капекс {company}, {period}, в $", round(usd, 2), "млрд $", period, "изчисление", FX_URL, "Х", f"{rmb} / {FX[fx_key]} (DEXCHUS {fx_key})")

    # Alibaba (фискална година до 31.03; паричен капекс по отчета)
    baba = {"Q1'24": 11153, "FY24": 32087, "Q1'25": 24612, "FY25": 85972, "Q2'25": 38676, "FY26": 126063, "Q1'26": 26887, "Q2'26": 67678}
    cap("Alibaba", "FY2024 (04.2023-03.2024)", baba["FY24"], U["baba_20f"], "В", "20-F FY2026, раздел Capital Expenditure", "2024")
    cap("Alibaba", "FY2025 (04.2024-03.2025)", baba["FY25"], U["baba_20f"], "В", "20-F FY2026", "2025")
    cap("Alibaba", "FY2026 (04.2025-03.2026)", baba["FY26"], U["baba_20f"], "В", "20-F FY2026; в отчета $18 275 млн", "2025")
    cap("Alibaba", "Q1 2024 (01-03.2024)", baba["Q1'24"], U["baba_q1_24"], "В", "6-K 14.05.2024", "2024")
    cap("Alibaba", "Q1 2025 (01-03.2025)", baba["Q1'25"], U["baba_q1_25"], "В", "6-K 15.05.2025", "2025")
    cap("Alibaba", "Q2 2025 (04-06.2025)", baba["Q2'25"], U["baba_q2_26"], "В", "6-K 20.08.2026 (сравнението г/г)", "2025Q2")
    cap("Alibaba", "Q1 2026 (01-03.2026)", baba["Q1'26"], U["baba_q1_26"], "В", "6-K 13.05.2026", "2026Q1")
    cap("Alibaba", "Q2 2026 (04-06.2026)", baba["Q2'26"], U["baba_q2_26"], "В", "6-K 20.08.2026; +75% г/г; в отчета $9 975 млн при 6,7851", "2026Q2")
    baba_h2_25 = baba["FY26"] - baba["Q2'25"] - baba["Q1'26"]
    baba_cy24 = baba["Q1'24"] + (baba["FY25"] - baba["Q1'25"])
    baba_cy25 = baba["Q1'25"] + baba["Q2'25"] + baba_h2_25
    baba_h1_26 = baba["Q1'26"] + baba["Q2'26"]
    baba_ltm = baba_h2_25 + baba["Q1'26"] + baba["Q2'26"]
    cap("Alibaba", "2024 календарна", baba_cy24, U["baba_20f"], "Х", "Q1'24 + (FY25 - Q1'25)", "2024")
    cap("Alibaba", "2025 календарна", baba_cy25, U["baba_20f"], "Х", "Q1'25 + Q2'25 + (FY26 - Q2'25 - Q1'26)", "2025")
    cap("Alibaba", "H1 2026", baba_h1_26, U["baba_q2_26"], "Х", "Q1'26 + Q2'26", "2026H1")
    cap("Alibaba", "последните 4 тримесечия (07.2025-06.2026)", baba_ltm, U["baba_q2_26"], "Х", "FY26 - Q2'25 + Q2'26", "LTM")

    # Tencent (календарна година)
    tc = {"FY24": 76760, "FY25": 79198, "Q2'25": 19107, "Q3'25": 12983, "Q4'25": 19632, "Q1'26": 31936, "Q2'26": 52784}
    cap("Tencent", "2024", tc["FY24"], U["tc_fy25"], "В", "годишните резултати 18.03.2026", "2024")
    cap("Tencent", "2025", tc["FY25"], U["tc_fy25"], "В", "годишните резултати 18.03.2026; +3% г/г", "2025")
    cap("Tencent", "Q2 2025", tc["Q2'25"], U["tc_q2_26"], "В", "резултатите за Q2 2026 (12.08.2026)", "2025Q2")
    cap("Tencent", "Q1 2026", tc["Q1'26"], U["tc_q2_26"], "В", "резултатите за Q2 2026", "2026Q1")
    cap("Tencent", "Q2 2026", tc["Q2'26"], U["tc_q2_26"], "В", "+176% г/г; оперативен капекс 51,8 млрд", "2026Q2")
    tc_h1_26 = tc["Q1'26"] + tc["Q2'26"]
    tc_ltm = tc["Q3'25"] + tc["Q4'25"] + tc_h1_26
    cap("Tencent", "H1 2026", tc_h1_26, U["tc_q2_26"], "Х", "Q1'26 + Q2'26", "2026H1")
    cap("Tencent", "последните 4 тримесечия (07.2025-06.2026)", tc_ltm, U["tc_fy25"], "Х", "Q3'25 12 983 + Q4'25 19 632 (В, годишните резултати) + H1'26", "LTM")
    add("Tencent: предплащания за изчислителна мощ в оперативния паричен поток, Q2 2026", 51.4, "млрд юана", "Q2 2026", "изчисление", U["tc_q2_26"], "Х",
        "FCF без предплащанията 37,6 минус отчетен FCF (-13,8); не са в капекса")

    # Baidu (календарна година)
    bd = {"FY24": 8134, "FY25": 12073, "Q1'25": 2900, "Q2'25": 3800, "Q3'25": 3401, "Q4'25": 1972, "Q1'26": 5916, "Q2'26": 11390}
    cap("Baidu", "2024", bd["FY24"], U["bidu_q4_25"], "В", "6-K 26.02.2026; същото в XBRL PaymentsToAcquirePropertyPlantAndEquipment", "2024")
    cap("Baidu", "2025", bd["FY25"], U["bidu_q4_25"], "В", "6-K 26.02.2026", "2025")
    cap("Baidu", "Q2 2025", bd["Q2'25"], U["bidu_q2_26"], "В", "6-K 18.08.2026", "2025Q2")
    cap("Baidu", "Q1 2026", bd["Q1'26"], U["bidu_q2_26"], "В", "6-K 18.08.2026", "2026Q1")
    cap("Baidu", "Q2 2026", bd["Q2'26"], U["bidu_q2_26"], "В", "6-K 18.08.2026; в отчета $1 679 млн", "2026Q2")
    bd_h1_26 = bd["Q1'26"] + bd["Q2'26"]
    bd_ltm = bd["Q3'25"] + bd["Q4'25"] + bd_h1_26
    cap("Baidu", "H1 2026", bd_h1_26, U["bidu_q2_26"], "Х", "Q1'26 + Q2'26", "2026H1")
    cap("Baidu", "последните 4 тримесечия (07.2025-06.2026)", bd_ltm, U["bidu_q4_25"], "Х", "Q3'25 3 401 + Q4'25 1 972 (В, 6-K 26.02.2026) + H1'26", "LTM")

    # Тримата заедно
    t24 = baba_cy24 + tc["FY24"] + bd["FY24"]
    t25 = baba_cy25 + tc["FY25"] + bd["FY25"]
    th1 = baba_h1_26 + tc_h1_26 + bd_h1_26
    tltm = baba_ltm + tc_ltm + bd_ltm
    tq2_26 = baba["Q2'26"] + tc["Q2'26"] + bd["Q2'26"]
    tq2_25 = baba["Q2'25"] + tc["Q2'25"] + bd["Q2'25"]
    cap("Alibaba+Tencent+Baidu", "2024 календарна", t24, "", "Х", "сбор", "2024")
    cap("Alibaba+Tencent+Baidu", "2025 календарна", t25, "", "Х", "сбор", "2025")
    cap("Alibaba+Tencent+Baidu", "H1 2026", th1, "", "Х", "сбор", "2026H1")
    cap("Alibaba+Tencent+Baidu", "последните 4 тримесечия (07.2025-06.2026)", tltm, "", "Х", "сбор", "LTM")
    cap("Alibaba+Tencent+Baidu", "Q2 2025", tq2_25, "", "Х", "сбор", "2025Q2")
    cap("Alibaba+Tencent+Baidu", "Q2 2026", tq2_26, "", "Х", "сбор", "2026Q2")
    add("Капекс Alibaba+Tencent+Baidu, Q2 2026 г/г в юани", r1((tq2_26 / tq2_25 - 1) * 100), "%", "Q2 2026", "изчисление", "", "Х", f"{tq2_26}/{tq2_25}-1")
    add("Капекс Alibaba+Tencent+Baidu, H1 2026 спрямо цялата 2025", r1(th1 / t25 * 100), "%", "H1 2026", "изчисление", "", "Х", f"{th1}/{t25}")
    us_q2 = 193.5   # описът, ред 231 (петимата с Oracle, В)
    us_h1 = 294.8   # описът, ред 232 (четиримата без Oracle, В)
    cn_q2_usd = tq2_26 / FX["2026Q2"] / 1000
    cn_h1_usd = th1 / FX["2026H1"] / 1000
    add("Капекс тримата китайски / петимата американски (с Oracle), Q2 2026", r1(cn_q2_usd / us_q2 * 100), "%", "Q2 2026", "изчисление", "", "Х", f"{round(cn_q2_usd,2)}/{us_q2} (описът, ред 231)")
    add("Капекс тримата китайски / четиримата американски (без Oracle), H1 2026", r1(cn_h1_usd / us_h1 * 100), "%", "H1 2026", "изчисление", "", "Х", f"{round(cn_h1_usd,2)}/{us_h1} (описът, ред 232)")

    # ByteDance (само прес, П)
    for period, rmb, url, note in [
        ("2025 план (Reuters, 23.01.2025)", 150000, U["bd_2025_reuters"], "над 150 млрд юана ($20,64 млрд); ByteDance го оспори: 'incorrect'"),
        ("2026 предварителен план (FT, 23.12.2025)", 160000, U["bd_2026_ft"], "160 млрд юана; по FT през Reuters/The Standard"),
        ("2026 план (SCMP, 09.05.2026)", 200000, U["bd_2026_scmp"], "над 200 млрд юана (около $30 млрд); SCMP 403, датата и числото през вторични (EqualOcean, TechNode)"),
    ]:
        capex_rows.append({"r": R, "company": "ByteDance", "period": period, "capex_rmb_mn": rmb, "fx_cny_per_usd": FX["2025" if "2025" in period[:4] else "2026H1"],
                           "fx_basis": "FRED DEXCHUS", "capex_usd_bn": round(rmb / FX["2025" if period.startswith("2025") else "2026H1"] / 1000, 2),
                           "source": url, "status": "П", "note": note})
        add(f"Капекс ByteDance, {period}", rmb, "млн юана", period, "прес", url, "П", note)
    capex_rows.append({"r": R, "company": "ByteDance", "period": "2026, обсъждан таван (Bloomberg)", "capex_rmb_mn": "", "fx_cny_per_usd": "",
                       "fx_basis": "", "capex_usd_bn": 70, "source": U["bd_2026_bbg"], "status": "П", "note": "до $70 млрд; Bloomberg през LDS 27.05.2026; разминава се с 200 млрд юана"})
    four25 = t25 / FX["2025"] / 1000 + 150000 / FX["2025"] / 1000
    add("Капекс четирите 2025 (Alibaba, Tencent, Baidu по отчет + ByteDance план по Reuters)", round(four25, 2), "млрд $", "2025", "изчисление", "", "Х",
        f"({t25} + 150 000) / {FX['2025']}; ByteDance е П и е оспорен от компанията")
    add("Капекс ByteDance 2026, обсъждан таван (Bloomberg)", 70, "млрд $", "27.05.2026", "прес", U["bd_2026_bbg"], "П", "разминава се със SCMP (около $30 млрд)")
    add("Alibaba: обещание за AI и облак за 3 години (от 24.02.2025)", 380000, "млн юана", "24.02.2025", "Alibaba Group", U["baba_380"], "В", "'at least RMB 380 billion ($53 billion) over the next three years'")
    spent = baba["FY26"] + baba["Q2'26"]
    add("Alibaba: изхарчен капекс 04.2025-06.2026 спрямо 380 млрд", r1(spent / 380000 * 100), "%", "Q2 2026", "изчисление", U["baba_q2_26"], "Х",
        "(FY26 " + str(baba["FY26"]) + " + Q2'26 " + str(baba["Q2'26"]) + ") / 380 000; целият капекс, не само AI")

    # ===== (д) официални данни и (е) примери =====
    off = [
        ("Държавен съвет 'AI+': цел за разпространение на интелигентни терминали и агенти до 2027", ">70", "%", "26.08.2025", "国发〔2025〕11号, gov.cn", U["govcn"], "В", "到2027年...应用普及率超70%"),
        ("Държавен съвет 'AI+': цел до 2030", ">90", "%", "26.08.2025", "国发〔2025〕11号, gov.cn", U["govcn"], "В", ""),
        ("Китай: дневна консумация на токени (词元), март 2026", ">140", "трлн токена на ден", "24.03.2026", "НАД (Лю Liehong) на пресконференция на ГИС, по Синхуа", U["nda"], "П", "Синхуа отворена; стенограмата не е"),
        ("Китай: дневна консумация на токени, края на 2025", 100, "трлн токена на ден", "24.03.2026", "НАД, по Синхуа", U["nda"], "П", ""),
        ("Китай: дневна консумация на токени, началото на 2024", 0.1, "трлн токена на ден", "24.03.2026", "НАД, по Синхуа", U["nda"], "П", "1000亿"),
        ("Google: токени на месец (всички продукти)", ">3200", "трлн токена на месец", "19.05.2026", "Google I/O 2026, Pichai", U["google_io"], "В", "'over 3.2 quadrillion per month'"),
        ("Google: токени на ден (приблизително)", 107, "трлн токена на ден", "19.05.2026", "изчисление", U["google_io"], "Х", "3 200 / 30"),
        ("МИИТ: дял на големите промишлени предприятия, ползващи AI", ">30", "%", "20.07.2026", "МИИТ (Wang Weiming) на пресконференция на ГИС, по Синхуа", U["miit"], "П", "规模以上制造业企业人工智能技术应用普及率超30%"),
        ("МИИТ: глобални сваляния на (китайските) отворени модели, натрупано", ">10", "млрд сваляния", "20.07.2026", "МИИТ, по Синхуа", U["miit"], "П", "人工智能开源大模型全球累计下载量突破100亿次"),
        ("CNNIC: потребители на генеративен AI в Китай, H1 2026", ">700", "млн души", "29.09.2026", "CNNIC, по ncsti.gov.cn/Наука и технологии дневник", U["cnnic"], "П", "普及率超50%"),
        ("CNNIC: разпространение на генеративния AI сред населението, H1 2026", ">50", "%", "29.09.2026", "CNNIC, по ncsti.gov.cn", U["cnnic"], "П", ""),
        ("CAICT: AI индустрия на Китай 2025", ">1 200", "млрд юана", "03.08.2026", "CAICT, по Чайна Нюз/China Daily", U["caict"], "П", "+40% г/г"),
        ("CAICT: приложният слой, дял от AI индустрията 2025", 55, "%", "03.08.2026", "CAICT, по China Daily", U["caict"], "П", "ръст +22% г/г"),
        ("CAICT: базовият слой (изчисления, чипове), дял 2025", 38, "%", "03.08.2026", "CAICT, по China Daily", U["caict"], "П", "ръст +59% г/г"),
        ("CAICT: слоят на моделите, дял 2025", 7, "%", "03.08.2026", "CAICT, по China Daily", U["caict"], "П", "ръст +189% г/г"),
        ("Alibaba: приходи от AI продукти, Q2 2026", 12376, "млн юана", "20.08.2026", "Alibaba 6-K", U["baba_q2_26"], "В", "трицифрен ръст г/г за 12-о поредно тримесечие"),
        ("Alibaba: потребители с първо AI пазаруване през Qwen app (от пускането)", 250, "млн души", "20.08.2026", "Alibaba 6-K", U["baba_q2_26"], "В", ""),
        ("Baidu: приходи от AI-powered Business, Q2 2026", 12.5, "млрд юана", "18.08.2026", "Baidu 6-K", U["bidu_q2_26"], "В", "половината от приходите на Baidu General Business; +25% г/г"),
        ("Baidu Apollo Go: градове", 28, "града", "18.08.2026", "Baidu 6-K", U["bidu_q2_26"], "В", ""),
        ("Baidu Apollo Go: изцяло без шофьор км, натрупано", 240, "млн км", "18.08.2026", "Baidu 6-K", U["bidu_q2_26"], "В", "общо автономни 350 млн км"),
        ("Финанси: China Merchants Bank, AI сценарии", 856, "сценария", "02.04.2026", "Daily Economic News (по годишните отчети)", U["banks"], "П", ""),
        ("Финанси: China Merchants Bank, заменени човекочасове 2025", 15.56, "млн часа", "02.04.2026", "Daily Economic News", U["banks"], "П", "около 8 000 души на пълен ден"),
        ("Финанси: шестте държавни банки, инвестиции във финтех 2025", ">130", "млрд юана", "02.04.2026", "Daily Economic News", U["banks"], "П", "2024: 125,459 млрд"),
        ("Администрация: Шънджън Футиен, AI 'служители' на DeepSeek", 70, "агента", "18.02.2025", "Beijing News (по 'Xingfu Futian')", U["futian"], "П", "240 сценария; времето за проверка на документи -90% (заявено от района)"),
        ("Производство: фабрики 'фар' на WEF в Китай", 101, "фабрики", "23.01.2026", "Yicai (по WEF)", U["wef_yicai"], "П", "от над 220 в света; 16 от около 23 нови през 01.2026; weforum.org върна 403"),
    ]
    for m, v, u, d, s, url, st, note in off:
        add(m, v, u, d, s, url, st, note)

    # ===== запис =====
    with open(f"{outdir}/china_ai_2026-10_chbd1g.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["r", "metric", "value", "unit", "as_of", "source", "url", "status", "note"])
        w.writeheader()
        w.writerows(rows)
    with open(f"{outdir}/china_capex_2026-10_chbd1g.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["r", "company", "period", "capex_rmb_mn", "fx_cny_per_usd", "fx_basis", "capex_usd_bn", "source", "status", "note"])
        w.writeheader()
        w.writerows(capex_rows)

    sys.stdout.reconfigure(encoding="utf-8")
    print("rows", len(rows), "capex rows", len(capex_rows))
    print("OR shares CN/US:", shares)
    print("OR top20 total", round(s_all, 2), "CN", round(s_cn, 2), r1(s_cn / s_all * 100), "US", round(s_us, 2), r1(s_us / s_all * 100),
          "flash/CN", r1(s_flash_cn / s_cn * 100), "top10 CN", r1(s_top10_cn / s_top10 * 100))
    print("OR weekly req 2025", round(tot_25 / 1e6), "M; 2026", round(tot_26 / 1e9, 2), "B; x", round(tot_26 / tot_25, 1))
    print("HF cn_llm", cn_llm, "west_llm", west_llm, "share", r1(cn_llm / (cn_llm + west_llm) * 100), "Qwen/Llama", round(o["Qwen"]["downloads_30d"] / o["meta-llama"]["downloads_30d"], 1))
    print("capex RMB mn: CY24", t24, "CY25", t25, "H1'26", th1, "LTM", tltm, "Q2'25", tq2_25, "Q2'26", tq2_26)
    for c in capex_rows:
        print(c["company"], "|", c["period"], "|", c["capex_rmb_mn"], "|", c["capex_usd_bn"])
    print("CN/US Q2", r1(cn_q2_usd / us_q2 * 100), "H1", r1(cn_h1_usd / us_h1 * 100), "Q2 yoy", r1((tq2_26 / tq2_25 - 1) * 100), "H1/CY25", r1(th1 / t25 * 100), "baba spent", r1(spent / 380000 * 100))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
