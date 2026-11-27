# Замразено на 2026-11-27 (ПРОЛЕТР9)

Решение на Ц. от 26.11.2026 (ПРОЛЕТМ2), прието в плана на 27.11.2026 (ПРОЛЕТР9): AI Hype става термометър с две стрелки (src/v2/strelki.py, out/weekly/<събота>.json), без зони, без скоростен флаг и без изваждане на печалбите; AI думите минават от ръчния корпус към пълнотекстовото търсене на SEC след проба.

Седмичният ход (`.github/workflows/weekly_v2.yml`) вече не пуска тези части. Нищо не е изтрито; данните
до датата на замразяването остават четими (в JSON файловете има ключ `frozen` с тази бележка).

| част | код | данни |
|---|---|---|
| зоните и журналът им | `src/v2/zones.py` | `app/data/v2/zones_retro.json`, `zone_journal.json` |
| разминаването G и фундаментът F | `src/v2/gap.py` | `app/data/v2/gap_series.json` |
| сборът E (четирите гласа) | `src/v2/euphoria.py` | `app/data/v2/euphoria_series.json` |
| „обещание срещу доставка“ | `src/v2/promise_delivery.py` | `app/data/v2/promise_delivery.json` |
| реториката от корпуса и корпусът | `src/v2/rhetoric_v2.py`, `src/build_corpus.py` | `app/data/v2/rhetoric_series.json`, `app/data/corpus/` |
| журналът на пукнатините и наблюдателите | `src/v2/watchers/`, `src/v2/falsifiers.py` | `app/data/v2/tripwires.yaml`, `out/watcher_*.md` |
| едностраничникът и лицето | `src/v2/onepager.py`, `src/v2/render_onepager_html.py` | `out/weekly/*.md` до 2026-11-21, старото лице в `docs/arhiv/2026-11-20/index.html` |

Живи остават: `multiple_v2.py` и `froth.py` (източници на стрелките), `collect_xbrl.py`, `strelki.py`, `ai_words.py` и `strelki_site.py` (от 27.11.2026 `docs/index.html` е публичната страница на двете стрелки, по решение на Ц. „Публичен сайт“).
Старият поток (`quarterly_nlp.yml`, `daily_update.yml`, `hype_index.json`) не е пипан и не се пуска.

Читател, който още чете замразен файл: `C:\Projects\markets\weekly-screen\build_storms.py` (бурята
„КАИШКАТА“ чете `euphoria_series.json`); не е пипан и показва датата на замразяването като своя.
