# ⚡ AI Hype Monitor

**Измерител на еуфорията в AI сектора** — автоматизиран дашборд, който следи здравословното състояние на AI индустрията от чипове до хиперскейлъри.

[![Daily Update](https://github.com/tsvetoslavtsachev/ai-hype-monitor/actions/workflows/daily_update.yml/badge.svg)](https://github.com/tsvetoslavtsachev/ai-hype-monitor/actions/workflows/daily_update.yml)
[![Quarterly NLP](https://github.com/tsvetoslavtsachev/ai-hype-monitor/actions/workflows/quarterly_nlp.yml/badge.svg)](https://github.com/tsvetoslavtsachev/ai-hype-monitor/actions/workflows/quarterly_nlp.yml)

🔗 **Live Dashboard:** [tsvetoslavtsachev.github.io/ai-hype-monitor](https://tsvetoslavtsachev.github.io/ai-hype-monitor)

---

## Какво измерва?

Репото следи три основни сигнала:

| Компонент | Тежест | Честота | Описание |
|-----------|--------|---------|----------|
| **Пазарен Momentum** | 40% | Дневно | 1Y процентил на цените + relative strength спрямо S&P 500 |
| **Rhetoric Score** | 40% | Тримесечно | Плътност на AI термини в SEC 8-K filings + substance ratio |
| **Valuation Stretch** | 20% | Дневно | Forward P/E спрямо историческа норма |

### AI Hype Score — Скала

| Score | Зона | Интерпретация |
|-------|------|---------------|
| 0–30 | ❄️ AI Winter | Охлаждане, разочарование |
| 30–50 | ⚖️ Балансиран | Рационален растеж |
| 50–70 | 📈 Повишен | Оптимизмът расте |
| 70–85 | 🔥 Hype | Еуфория, внимание |
| 85–100 | 💥 Балон | Прегряване, исторически риск |

---

## AI Value Chain — Следени Компании

### Слой 1: Semiconductor Equipment
ASML · AMAT · LRCX · KLAC · ONTO

### Слой 2: Chip Design
NVDA · AMD · AVGO · MRVL · ARM · QCOM · SNPS · CDNS

### Слой 3: Memory & Storage
MU · WDC · STX

### Слой 4: Networking & Optics
ANET · CIEN · COHR · LITE · FN

### Слой 5: Infrastructure & Power
VRT · ETN · DELL · SMCI · PWR

### Слой 6: Hyperscalers
MSFT · GOOGL · AMZN · META · ORCL

### Слой 7: AI Software
PLTR · CRM · NOW · SNOW · AI

### AI ETF-и (от price-archive)
SMH · SOXX · AIQ · BOTZ · ROBO · WCLD · CLOU · ARKK

---

## Архитектура

```
ai-hype-monitor/
├── .github/workflows/
│   ├── daily_update.yml      # Дневен cron (22:30 UTC, пон-пет)
│   ├── quarterly_nlp.yml     # Седмичен cron (понеделник 06:00 UTC)
│   └── deploy_pages.yml      # GitHub Pages deploy при push
│
├── config/
│   ├── universe.csv          # AI Value Chain тикъри
│   └── keywords.json         # NLP речник (AI термини, substance, uncertainty)
│
├── src/
│   ├── fetch_prices.py       # Цени от price-archive + yfinance
│   ├── fetch_sec_edgar.py    # 8-K filings от SEC EDGAR (безплатно)
│   ├── analyze_rhetoric.py   # NLP анализ на AI rhetoric
│   ├── calc_hype_index.py    # Композитен AI Hype Score
│   └── run_pipeline.py       # Оркестратор (--daily / --quarterly)
│
└── app/                      # GitHub Pages Root
    ├── index.html
    ├── css/style.css
    ├── js/app.js
    └── data/                 # Автоматично обновявани JSON
        ├── hype_index.json
        ├── hype_history.json
        ├── daily_prices.json
        └── rhetoric.json
```

---

## Стартиране

### Изисквания
```bash
pip install -r requirements.txt
```

### Дневен pipeline (цени + hype index)
```bash
python src/run_pipeline.py --daily \
  --price-archive-root ../price-archive
```

### Quarterly pipeline (+ SEC filings + NLP)
```bash
python src/run_pipeline.py --quarterly \
  --price-archive-root ../price-archive
```

---

## Настройка на GitHub Pages

1. Отиди в **Settings → Pages**
2. Source: **GitHub Actions**
3. Workflow `deploy_pages.yml` ще се стартира автоматично при всеки push

---

## Данни

- **Цени на акции:** [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance)
- **ETF цени:** [tsvetoslavtsachev/price-archive](https://github.com/tsvetoslavtsachev/price-archive)
- **SEC Filings:** [SEC EDGAR API](https://www.sec.gov/developer) (безплатно, без API ключ)
- **NLP:** Lexicon-based анализ (без ML модел — детерминистичен и прозрачен)

---

## Методология

Rhetoric Score измерва **разминаването между наратива и реалността** в AI сектора. Той се базира на три лексикона:

- **AI Hype Terms** (40 термина): "generative AI", "LLM", "AI-powered", "AI supercycle"...
- **Substance Terms** (25 термина): "revenue", "gross margin", "capex", "ROI", "bookings"...
- **Uncertainty Terms** (15 термина): "exploring", "potential", "believe", "transformative"...

Висок Rhetoric Score означава, че директорите говорят много за AI, но с малко финансова конкретика — класически признак на hype.

---

## Автор

**Цветослав Цачев** — финансов анализатор, Елана Трейдинг | Bloomberg TV България

*Информацията е само за аналитични цели и не представлява инвестиционен съвет.*
