"""
facts_store.py — PIT loader за F-крак фактите (Фаза 1, + TTM идентичност).
=========================================================================
Чете app/data/v2/facts/{TICKER}.json (bitemporal) и връща стойности по
Point-In-Time правилото: НИКОГА не издава запис с known_at (filed) > as_of_date.

Хранилището пази ВСИЧКИ дюрации (Q + H/9M YTD + FY). Тримесечните четения
(get_asof/get_series) филтрират по period_type (default "Q" за flow концепти,
"instant" за shares). `ttm_asof` смята trailing-12M чрез счетоводна ИДЕНТИЧНОСТ
от официални факти (не прокси):
    TTM(край на Qk) = FY_предх + YTD_k_текуща − YTD_k_минала     ⟺   Q4 = FY − 9M
PIT за derived: known_at = max(known_at на компонентите); `derived_from` дава
одитна следа кои факти участват (plus/minus).

Датите са ISO низове (YYYY-MM-DD) — сравняват се лексикографски (коректно).
"""

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

try:  # работи и като модул (src.v2), и standalone
    from concepts import tag_priority, period_type, period_days, CONCEPT_KIND
except ImportError:  # pragma: no cover
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from concepts import tag_priority, period_type, period_days, CONCEPT_KIND

FACTS_DIR = Path(__file__).resolve().parents[2] / "app" / "data" / "v2" / "facts"


def _facts_path(ticker: str) -> Path:
    return FACTS_DIR / f"{ticker}.json"


@lru_cache(maxsize=None)
def load(ticker: str) -> dict:
    """Целият facts обект за тикера ({} ако липсва). Кеширан — не мутирай резултата."""
    p = _facts_path(ticker)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def records(ticker: str, concept: str = None) -> list:
    facts = load(ticker).get("facts", [])
    if concept is not None:
        facts = [r for r in facts if r["concept"] == concept]
    return facts


def _ptype(r: dict) -> str:
    return period_type(r["period_start"], r["period_end"])


def _pdays(r: dict) -> int:
    if r["period_start"] == r["period_end"]:
        return 0
    return period_days(r["period_start"], r["period_end"])


def _best_vintage(recs: list) -> dict:
    """Най-скорошен known_at; при равен known_at — най-приоритетен таг."""
    return sorted(
        recs,
        key=lambda r: (r["known_at"], -tag_priority(r["concept"], r["xbrl_tag"])),
    )[-1]


def _default_period(concept: str) -> str:
    return "instant" if CONCEPT_KIND.get(concept) == "instant" else "Q"


def _pit_period_recs(ticker, concept, as_of, period):
    return [r for r in records(ticker, concept)
            if r["known_at"] <= as_of and _ptype(r) == period]


def get_asof(ticker: str, concept: str, as_of_date: str, period: str = None):
    """Последната (най-скорошен период) стойност, ИЗВЕСТНА към as_of_date.

    period: тип на периода ("Q" тримесечно [default за flow], "instant" за
    shares, или "FY"/"H"/"9M"). PIT: known_at ≤ as_of; после най-скорошен
    period_end, най-скорошен винтидж, най-приоритетен таг. Връща записа или None.
    """
    period = period or _default_period(concept)
    recs = _pit_period_recs(ticker, concept, as_of_date, period)
    if not recs:
        return None
    latest_pe = max(r["period_end"] for r in recs)
    return _best_vintage([r for r in recs if r["period_end"] == latest_pe])


def get_series_asof(ticker: str, concept: str, as_of_date: str, period: str = None) -> dict:
    """{period_end: value} по PIT — по един (най-добър винтидж) на период."""
    period = period or _default_period(concept)
    recs = _pit_period_recs(ticker, concept, as_of_date, period)
    by_period = {}
    for r in recs:
        by_period.setdefault(r["period_end"], []).append(r)
    return {pe: _best_vintage(rs)["value"] for pe, rs in sorted(by_period.items())}


def latest(ticker: str, concept: str, period: str = None):
    """Най-скорошната known стойност изобщо (as_of = безкрайно бъдеще)."""
    return get_asof(ticker, concept, "9999-12-31", period)


# ── TTM (trailing 12M) чрез счетоводна ИДЕНТИЧНОСТ ──────────────────────────

def _best_by_period(ticker, concept, as_of):
    """PIT best-vintage duration факти -> {(start,end): record}."""
    recs = [r for r in records(ticker, concept)
            if r["known_at"] <= as_of and r["period_start"] != r["period_end"]]
    groups = {}
    for r in recs:
        groups.setdefault((r["period_start"], r["period_end"]), []).append(r)
    return {k: _best_vintage(v) for k, v in groups.items()}


def _four_quarters(best: dict, E: str):
    """4 съседни тримесечия, завършващи на E (contiguous). None ако не са налични."""
    by_end = {k[1]: r for k, r in best.items() if _ptype(r) == "Q"}
    chain, cur_end = [], E
    for _ in range(4):
        r = by_end.get(cur_end)
        if r is None:
            return None
        chain.append(r)
        cur_end = (date.fromisoformat(r["period_start"]) - timedelta(days=1)).isoformat()
    return list(reversed(chain))


def _ttm_result(value, plus, minus, method):
    comps = [(p, "plus") for p in plus] + [(m, "minus") for m in (minus or [])]
    known_at = max(c["known_at"] for c, _ in comps)
    derived_from = [{
        "role": role, "period_start": c["period_start"], "period_end": c["period_end"],
        "value": c["value"], "known_at": c["known_at"], "accn": c["accn"],
    } for c, role in comps]
    return {"value": value, "known_at": known_at, "method": method,
            "derived_from": derived_from}


def ttm_asof(ticker: str, concept: str, as_of_date: str):
    """Trailing-12M към as_of чрез идентичност от официални факти (PIT-чисто).

    (1) сума на 4 съседни тримесечия, ако са налични; иначе
    (2) идентичност TTM = FY_предх + YTD_текуща − YTD_минала (⟺ Q4 = FY − 9M).
    Връща {value, known_at, method, derived_from} или None (видима непълнота).
    Само за flow концепти (не за instant shares).
    """
    if CONCEPT_KIND.get(concept) != "duration":
        return None
    best = _best_by_period(ticker, concept, as_of_date)
    if not best:
        return None
    quarters = {k: r for k, r in best.items() if _ptype(r) == "Q"}
    if not quarters:
        # без тримесечия: ако има FY факт — TTM = последният FY
        fys = {k: r for k, r in best.items() if _ptype(r) == "FY"}
        if not fys:
            return None
        E = max(k[1] for k in fys)
        r = _best_vintage([v for k, v in fys.items() if k[1] == E])
        return _ttm_result(r["value"], [r], None, "fy_only")

    E = max(k[1] for k in quarters)

    # (1) сума на 4 съседни тримесечия
    chain = _four_quarters(best, E)
    if chain:
        return _ttm_result(sum(r["value"] for r in chain), chain, None, "sum_4q")

    # (2) счетоводна идентичност
    ending_E = [r for k, r in best.items() if k[1] == E]
    ytd_cur = max(ending_E, key=_pdays)
    if _ptype(ytd_cur) == "FY":              # E е фискален край -> TTM = FY
        return _ttm_result(ytd_cur["value"], [ytd_cur], None, "fy_direct")

    fys = ytd_cur["period_start"]
    P = (date.fromisoformat(fys) - timedelta(days=1)).isoformat()
    fy_prior = [r for k, r in best.items() if k[1] == P and _ptype(r) == "FY"]
    if not fy_prior:
        return None                           # не може да се деривира -> None
    fyp = _best_vintage(fy_prior)
    prior_fys = fyp["period_start"]
    cur_days = _pdays(ytd_cur)
    prior_cands = [r for k, r in best.items() if k[0] == prior_fys]
    if not prior_cands:
        return None
    ytd_prior = min(prior_cands, key=lambda r: abs(_pdays(r) - cur_days))
    if abs(_pdays(ytd_prior) - cur_days) > 15:
        return None
    value = fyp["value"] + ytd_cur["value"] - ytd_prior["value"]
    return _ttm_result(value, [fyp, ytd_cur], [ytd_prior], "identity")
