"""
series_util.py — споделени помощници за Е-крак сериите (Фаза 2).
================================================================
Робастен z (median/MAD) с РАЗШИРЯВАЩ СЕ прозорец (PIT-съвместим, без look-ahead)
+ календарно-тримесечни помощници. Един източник, за да няма разминаване между
четирите гласа.

Робастен z: z_t = (x_t − median(hist)) / (1.4826 · MAD(hist)), където hist е
наличната история ДО и ВКЛЮЧИТЕЛНО t. None ако: <min_history точки, x_t е None,
или MAD == 0 (недефинирана скала). 1.4826 прави MAD ≈ σ при нормалност.
"""

from datetime import date

MAD_SCALE = 1.4826


def _median(xs: list):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def robust_z(x, history: list):
    """z на x спрямо history (median/MAD). None при празна/нулева скала."""
    hist = [h for h in history if h is not None]
    if x is None or not hist:
        return None
    med = _median(hist)
    mad = _median([abs(h - med) for h in hist])
    if mad is None or mad == 0:
        return None
    return (x - med) / (MAD_SCALE * mad)


def expanding_robust_z(values: list, min_history: int = 8) -> list:
    """Списък от z по разширяващ се прозорец (hist = values[0..i], вкл. i).

    z_i = None ако наличните (не-None) точки до i са < min_history или MAD==0.
    """
    out = []
    for i in range(len(values)):
        hist = [v for v in values[: i + 1] if v is not None]
        if len(hist) < min_history or values[i] is None:
            out.append(None)
        else:
            out.append(robust_z(values[i], hist))
    return out


# ── календарно тримесечие ───────────────────────────────────────────────────

def calendar_quarter(d: str) -> str:
    """'2024-05-14' -> '2024Q2' (по КАЛЕНДАРНАТА дата, не фискален етикет)."""
    y, m, _ = d.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def quarter_end_date(q: str) -> str:
    """'2024Q2' -> '2024-06-30' (край на календарното тримесечие)."""
    y, qn = q.split("Q")
    ends = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
    return f"{y}-{ends[qn]}"


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return (int(y), int(qn))


def quarters_between(q_start: str, q_end: str) -> list:
    """Всички календарни тримесечия в [q_start, q_end] включително."""
    ys, qs = map(int, q_start.split("Q"))
    ye, qe = map(int, q_end.split("Q"))
    out = []
    y, qn = ys, qs
    while (y, qn) <= (ye, qe):
        out.append(f"{y}Q{qn}")
        qn += 1
        if qn > 4:
            qn, y = 1, y + 1
    return out
