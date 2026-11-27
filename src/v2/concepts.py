"""
concepts.py — споделена дефиниция на F-крак концептите (Фаза 1).
================================================================
ЕДИН източник на истина за fallback веригите (използва се и от collect_xbrl.py,
и от facts_store.py — за да няма два разминаващи се списъка). Приоритетът е
редът в списъка: индекс 0 = най-висок приоритет. Per-период резолюцията взима
най-високоприоритетния таг, който има факт за този период.

IFRS еквивалентите са НАЙ-НИСЪК приоритет (чуждестранни емитенти: ASML, ARM).
Ако нищо от веригата няма факт → стойността е None (никакво импровизирано прокси).
"""

# логически концепт -> подредена fallback верига от XBRL тагове (namespace:tag)
CONCEPT_CHAINS = {
    "revenue": [
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
        "ifrs-full:Revenue",
    ],
    "gross_profit": [
        "us-gaap:GrossProfit",
        "ifrs-full:GrossProfit",
    ],
    "operating_income": [
        "us-gaap:OperatingIncomeLoss",
        "ifrs-full:ProfitLossFromOperatingActivities",
    ],
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        # ПРОЛЕТР9: AMZN след 2017 (сменен таг); панелът на stock-selection има същия ред.
        "us-gaap:PaymentsToAcquireProductiveAssets",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    ],
    "eps_diluted": [
        "us-gaap:EarningsPerShareDiluted",
        "ifrs-full:DilutedEarningsLossPerShare",
    ],
    "shares": [
        "dei:EntityCommonStockSharesOutstanding",
        # ПРОЛЕТР9: емитентите с няколко класа (GOOGL, DELL, PLTR) нямат dei без измерение
        # в companyfacts; балансовият брой е резервата.
        "us-gaap:CommonStockSharesOutstanding",
        # ПРОЛЕТР9: META няма и двата; средно претеглените разводнени акции за тримесечието,
        # като точка в края му (виж DURATION_AS_INSTANT). Последна резерва, с бележка в изхода.
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
}

# Тагове, които са дюрация в XBRL, но се пазят като точка в края на периода за instant
# концепт. Взимат се само тримесечните им факти (QUARTER_MIN_DAYS..QUARTER_MAX_DAYS).
DURATION_AS_INSTANT = {"us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding"}

# За instant концепт (броя акции) тагът се избира преди периода: най-приоритетният таг,
# чийто последен период е до толкова дни по-стар от най-скорошния период изобщо.
# Така имената с dei остават на dei (нищо не се мести за тях), а остарял dei не държи
# името на стара стойност, когато балансовият брой е по-нов.
INSTANT_TAG_FRESH_DAYS = 120

# duration = flow (period start..end); instant = единичен момент (само end)
CONCEPT_KIND = {
    "revenue": "duration",
    "gross_profit": "duration",
    "operating_income": "duration",
    "capex": "duration",
    "eps_diluted": "duration",
    "shares": "instant",
}

# тримесечен прозорец за duration факти (дни между start и end)
QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100


def tag_priority(concept: str, xbrl_tag: str) -> int:
    """Индекс на тага в веригата (по-малък = по-приоритетен). Непознат → голям."""
    chain = CONCEPT_CHAINS.get(concept, [])
    return chain.index(xbrl_tag) if xbrl_tag in chain else len(chain)


def period_days(period_start: str, period_end: str) -> int:
    """Дни в периода (0 за instant, където start == end)."""
    from datetime import date
    return (date.fromisoformat(period_end) - date.fromisoformat(period_start)).days


# Класификация на дюрацията. Тримесечните серии остават Q; H/9M/FY се пазят,
# за да е възможна счетоводната ИДЕНТИЧНОСТ за TTM/Q4 (не прокси):
#   TTM(край на Qk) = FY_прев + YTD_k_текуща - YTD_k_минала  ⟺  Q4 = FY - 9M.
def period_type(period_start: str, period_end: str) -> str:
    if period_start == period_end:
        return "instant"
    d = period_days(period_start, period_end)
    if QUARTER_MIN_DAYS <= d <= QUARTER_MAX_DAYS:
        return "Q"
    if 170 <= d <= 195:
        return "H"      # 6-месечно YTD (2 тримесечия)
    if 260 <= d <= 285:
        return "9M"     # 9-месечно YTD (3 тримесечия)
    if 350 <= d <= 380:
        return "FY"     # 12-месечно
    return "other"
