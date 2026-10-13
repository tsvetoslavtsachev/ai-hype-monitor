"""ЧБД1г Р2: китайските отворени модели срещу американските (Hugging Face сваляния + OpenRouter цени).

Употреба:
    python -I chbd1g_china_models.py <out_dir>

Тегли:
  1) Hugging Face публичното API (https://huggingface.co/api/models?author=<org>), всички модели на
     организацията, полета downloads (последните 30 дни), downloadsAllTime, likes; сумира по организация,
     дава топ модела и разпределението на 30-дневните сваляния по размер (параметри от името на модела).
  2) OpenRouter https://openrouter.ai/api/v1/models: цени вход/изход в $ за 1 млн токена за избран списък
     модели (котировката на OpenRouter, базовият доставчик; не е непременно официалната цена на лабораторията).
Пише <out_dir>/hf_orgs.json, <out_dir>/or_prices.json и печата кратък извод.
Сваляния по света (HF не дава държава); преброяват се само репата на самата организация (без квантовани
копия от трети страни като unsloth/bartowski).
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

UA = "chbd1g research contact@example.com"
HF_ORGS = {
    # китайски
    "Qwen": "CN", "deepseek-ai": "CN", "moonshotai": "CN", "zai-org": "CN", "THUDM": "CN",
    "MiniMaxAI": "CN", "baidu": "CN", "tencent": "CN", "ByteDance-Seed": "CN",
    # американски / европейски
    "meta-llama": "US", "google": "US", "mistralai": "EU", "openai": "US",
}
OR_MODELS = [
    "openai/gpt-6-astra", "openai/gpt-6.1-sol", "anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5",
    "~google/gemini-pro-latest", "google/gemini-3.1-pro-preview", "x-ai/grok-4.7",
    "deepseek/deepseek-v4-pro-0813", "deepseek/deepseek-v4.1-flash", "qwen/qwen3.8-max-0902",
    "qwen/qwen3.8-max-prime", "moonshotai/kimi-k3", "z-ai/glm-5.3", "minimax/minimax-m3",
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        link = r.headers.get("Link", "")
        return json.loads(r.read().decode("utf-8")), link


def size_b(model_id):
    """Общ брой параметри в млрд по името (напр. Qwen3-30B-A3B -> 30); None ако го няма."""
    name = model_id.split("/", 1)[1]
    for m in re.finditer(r"(?<![A-Za-z])(\d+(?:\.\d+)?)\s*([BbMm])(?![a-zA-Z])", name):
        start = m.start()
        if start > 0 and name[start - 1] in "Aa":  # активни параметри при MoE
            continue
        v = float(m.group(1))
        return v / 1000 if m.group(2) in "Mm" else v
    for m in re.finditer(r"(\d+(?:\.\d+)?)[Tt](?![a-zA-Z])", name):
        return float(m.group(1)) * 1000
    return None


def bucket(s):
    if s is None:
        return "без размер в името"
    if s <= 10:
        return "до 10 млрд"
    if s <= 40:
        return "10-40 млрд"
    if s <= 150:
        return "40-150 млрд"
    return "над 150 млрд"


def hf_org(org):
    url = (f"https://huggingface.co/api/models?author={org}&sort=downloads&direction=-1&limit=1000"
           "&expand[]=downloads&expand[]=downloadsAllTime&expand[]=likes&expand[]=createdAt")
    out = []
    while url:
        data, link = get(url)
        out.extend(data)
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
        time.sleep(0.5)
    return out


def main(out_dir):
    pulled = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    orgs = {}
    for org, region in HF_ORGS.items():
        try:
            ms = hf_org(org)
        except Exception as e:  # noqa: BLE001
            orgs[org] = {"region": region, "error": str(e)}
            continue
        d30 = sum(m.get("downloads") or 0 for m in ms)
        dall = sum(m.get("downloadsAllTime") or 0 for m in ms)
        likes = sum(m.get("likes") or 0 for m in ms)
        top = max(ms, key=lambda m: m.get("downloads") or 0) if ms else {}
        buckets = {}
        for m in ms:
            b = bucket(size_b(m["id"]))
            buckets[b] = buckets.get(b, 0) + (m.get("downloads") or 0)
        rec = {"region": region, "n_models": len(ms), "downloads_30d": d30, "downloads_all_time": dall,
               "likes": likes, "top_model": top.get("id"), "top_model_downloads_30d": top.get("downloads"),
               "downloads_30d_by_size": buckets}
        if org == "google":
            g = [m for m in ms if "gemma" in m["id"].lower()]
            rec["gemma_downloads_30d"] = sum(m.get("downloads") or 0 for m in g)
            rec["gemma_downloads_all_time"] = sum(m.get("downloadsAllTime") or 0 for m in g)
            rec["gemma_n_models"] = len(g)
        if org == "openai":
            g = [m for m in ms if "gpt-oss" in m["id"].lower()]
            rec["gpt_oss_downloads_30d"] = sum(m.get("downloads") or 0 for m in g)
        orgs[org] = rec
    json.dump({"pulled_utc": pulled, "orgs": orgs}, open(f"{out_dir}/hf_orgs.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    data, _ = get("https://openrouter.ai/api/v1/models")
    by_id = {m["id"]: m for m in data["data"]}
    prices = {}
    for mid in OR_MODELS:
        m = by_id.get(mid)
        if not m:
            prices[mid] = None
            continue
        p = m["pricing"]
        prices[mid] = {"name": m.get("name"), "canonical": m.get("canonical_slug"),
                       "in_usd_per_m": round(float(p["prompt"]) * 1e6, 4),
                       "out_usd_per_m": round(float(p["completion"]) * 1e6, 4),
                       "created": datetime.fromtimestamp(m.get("created", 0), timezone.utc).strftime("%Y-%m-%d")}
    json.dump({"pulled_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "n_models": len(data["data"]),
               "prices": prices}, open(f"{out_dir}/or_prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    cn = sum(v.get("downloads_30d", 0) for v in orgs.values() if v.get("region") == "CN")
    west = sum(v.get("downloads_30d", 0) for v in orgs.values() if v.get("region") in ("US", "EU"))
    print("HF pulled", pulled)
    for k, v in orgs.items():
        print(f"{k:15s} {v.get('region')} n={v.get('n_models')} d30={v.get('downloads_30d')} "
              f"all={v.get('downloads_all_time')} top={v.get('top_model')} ({v.get('top_model_downloads_30d')})")
    print("CN d30", cn, "US/EU d30", west, "CN share", round(cn / (cn + west) * 100, 2) if cn + west else None)
    for k, v in prices.items():
        print(k, v and (v["in_usd_per_m"], v["out_usd_per_m"]))


if __name__ == "__main__":
    main(sys.argv[1])
