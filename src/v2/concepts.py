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
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    ],
    "eps_diluted": [
        "us-gaap:EarningsPerShareDiluted",
        "ifrs-full:DilutedEarningsLossPerShare",
    ],
    "shares": [
        "dei:EntityCommonStockSharesOutstanding",
    ],
}

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
