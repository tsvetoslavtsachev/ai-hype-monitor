"""
t10_depreciation.py — watcher за T10 (амортизационни допускания), Фаза 4 (4.2).
==============================================================================
STUB (v1 = документирана процедура + годишно напомняне, БЕЗ автоматика).

T10: смяна на амортизационни допускания НАДОЛУ (по-къс useful-life на сървъри/GPU)
от ВТОРИ хиперскейлър. Това е годишно 10-K събитие, не месечно, и изисква
четене на "Property and Equipment / useful lives" бележката — твърде рядко и
контекстуално за автоматика в v1.

ПРОЦЕДУРА (ръчна, годишна):
  1. За всеки хиперскейлър (MSFT, GOOGL, AMZN, META, ORCL) вземи последния 10-K.
  2. Намери useful-life за servers / network equipment (обикновено 4-6 години).
  3. Сравни с миналогодишния 10-K. Съкращаване НАДОЛУ = сигнал.
  4. Amazon вече мина 6->5 г. (обратно на другите). T10 пали при ВТОРИ такъв ход.
  5. Ръчно потвърждение -> смяна на статуса в tripwires.yaml.

Watcher-ът НЕ прави мрежови заявки и НЕ сменя статус. Само пише напомнянето.
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out" / "watcher_t10.md"

HYPERSCALERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Watcher T10 (depreciation useful-life) — STUB / annual manual procedure",
        "",
        "No automation in v1 (annual 10-K useful-life note diff; too rare/contextual).",
        f"- Hyperscalers to check (10-K 'useful lives' for servers/network): {HYPERSCALERS}",
        "- Amazon already moved 6->5y; T10 fires on a SECOND hyperscaler cutting downward.",
        "- Procedure documented in the module docstring; human confirms and sets status.",
        "- ANNUAL REMINDER (set a calendar note; not fired automatically).",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[t10_depreciation] stub reminder written -> {OUT.name}")


if __name__ == "__main__":
    main()
