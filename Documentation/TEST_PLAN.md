# TEST_PLAN — Auraloom

Уровни проверок A–E. Для каждого — команда и фактический результат на
2026-11-16 (Windows, Python 3.14, PySide6 6.12, `main` @ `9fc19e4` + рабочая
директория).

Окружение: `QT_QPA_PLATFORM=windows` для визуальных проверок (offscreen даёт
«тофу» вместо шрифтов), `offscreen` — для логических.

## Уровень A — Static

| Проверка | Команда | Результат |
|---|---|---|
| Компиляция Python | `python -m compileall -q app` | PASS (без ошибок) |
| Юнит-тесты | `python -m unittest discover -s tests -q` | PASS — 152 теста (вкл. 3 в `test_mt_quality.py`, 4 в `test_bridge_monitor.py`) |
| QML-линт | `pyside6-qmllint -I app/qtapp/qml app/qtapp/qml/main.qml app/qtapp/qml/pages/*.qml app/qtapp/qml/RedZ/*.qml` | PASS — 0 ошибок (только Info/Warning) |
| Аудит API QML→Python | обход всех `appState.*`, `liveEngine.*`, `voiceController.*`, `*Model.*` в QML и `hasattr` на живых объектах | PASS — 74 обращения, 0 отсутствующих |
| Аудит сигналов | AST: сравнение арности `Signal(...)` и `.emit(...)` | PASS — 0 расхождений (было 2, исправлено) |
| Запуск QML-оболочки | `python app/qtapp/test_launch.py` | PASS — «окно создано и показано, QML OK» |

## Уровень B — Integration

| Проверка | Как | Результат |
|---|---|---|
| Состояние движка доходит до UI | `live._set_state("LOADING"/"READY")` → `appState.engineState` | PASS |
| Ошибка движка доходит до UI | `_set_state("ERROR", msg)` → `engineState`, `engineError` | PASS |
| Уровень микрофона → QML | `live._level = 0.5`, `_emit_level()` → `page.micLevel` | PASS |
| Устройства → движок | `setInDevice` → `live._mic_idx` | PASS (в обе стороны) |
| Громкость → движок | `setVoiceVolume(120)` → `live._volume = 1.2` | PASS |
| История: out / in | `textReady` / `peerTextReady` → `HistoryModel` | PASS |
| Фразы: add/delete | `addPhrase` → 33→34, `deletePhrase` → 33 | PASS |
| Загрузка всех страниц | переключение `section` в `main.qml` | PASS — 5/5 |
| Настройки | `setHints/setAutoStartEngine/setFullscreen` + `ui_settings.json` | PASS |
| PCM собеседника: bytes и float32 | `send_peer_pcm(bytes\|ndarray, sr)` | PASS — раньше bytes падали в `np.clip` и звук молча терялся |
| Нарезка речи собеседника | синтетические блоки 48 кГц | PASS — фраза уходит, тишина нет, куски ≤ 5 с |
| Защита от петли | `_incoming_active = True` → подача звука | PASS — в движок ничего не уходит |
| Входящее аудио — только наушники | `_emit_incoming_audio` с мостом | PASS — `_play_queue` (кабель) пуст |
| Отчёт о моделях | `Engine.models_info()` | PASS — список+направления+признак `installed` |
| Языки/входящий перевод в настройках | `setPeerLang/setIncomingVolume/setIncoming` | PASS — записаны и прочитаны |

## Уровень C — Runtime

| Сценарий | Как проверялось | Результат |
|---|---|---|
| Запуск интерфейса | `test_launch.py`, скриншоты разделов | PASS |
| Кэш переводов | два одинаковых `translate_text` на живой модели | PASS — 311 мс → 0,0 мс, `cache_hits=1`; тесты на границы и ключ языка |
| Глоссарий терминов | `translate_to_ru` en→ru с включённым `glossary.py` | PASS — термины на месте («Блэкуотер», «Артур Морган»); метка `⟦G0⟧` отбракована — opus-mt её искажает |
| История на диске и экспорт | `tests/test_history_store.py` (tempfile), кнопки в UI | PASS — 6 тестов; отбрасывание старых записей, битые строки, JSON/TXT |
| Клавиатурная навигация | `tools/nav_key_check.py`: Tab → Down ×2 → Enter, затем Up → Space | PASS — home → voices → live, QTest в offscreen |
| «Голос»: панель инструментов в 1280 px | скриншот после разбивки на два ряда | PASS — поле имени профиля и «Создать профиль» видны целиком, `shots/voices_1280x840.png` |
| «История» с записями | `tools/history_shot.py` наполняет модель четырьмя репликами | PASS — карточки, направления (RU→ES / ES→RU), время, действия; `shots/history_filled_1280x840.png`, `shots/history_filled_1920x1080.png` |
| IT→RU через английский | движковый python: `opus-mt-it-en` + `opus-mt-en-ru`, 3 фразы, beam 4 | PASS — «Non toccare niente, per favore!» → «Ничего не трогай, пожалуйста!»; в одной фразе потерян вопрос «Где ты?» (потеря на pivot) |
| EXE после ребрендинга | `pyinstaller --clean --noconfirm app/redz_voice_studio.spec`, запуск, скриншот | PASS — `dist/RedZVoiceStudio.exe` 301 МБ, окно `Auraloom`, новый UI рендерится (`shots/exe_launch.png`) |
| Все 7 экранов в двух разрешениях | скриншоты 1280×840 и 1920×1080 для главной, перевода, голоса, моделей, настроек, истории, фраз | PASS — `shots/*_1280x840.png`, `shots/*_1920x1080.png`; пустые состояния истории — ожидаемо |
| Запуск движка | `state.startEngine()` | PASS — `LOADING` 0.2 с, `READY` 20.4 с |
| Загрузка моделей (лог) | `live_engine.log` | PASS — ASR+MT 7.1 с, XTTS 10.4 с, RSS 2.1 ГБ |
| Остановка движка | `state.stopEngine()` | PASS — `STOPPING` → `STOPPED`, «движок остановлен» |
| Крах движка | внешний `kill` процесса | PASS — `ERROR` «движок остановился», ложных ошибок нет |
| Повторный запуск после краха | `startEngine()` после ERROR | PASS — `READY` через 22 с |
| Сквозной пайплайн | `reference.wav` (22.5 с, 44.1 кГц) → `translate_pcm` | PASS — ASR 11 фраз, перевод на испанский, TTS-чанки получены |
| PTT | `pressToTalk()` | PASS — вход открыт, 22 замера уровня, закрыт по отпусканию |
| Непрерывный режим | `setContinuous(True)` | PASS — вход открыт, лог «включён» |
| Индикатор уровня | синтетические блоки | PASS — тишина 0 %, речь 45 %, громко 60 % |
| Микрофон по умолчанию | `refreshDevices` | PASS — выбран fifine, маппер пропущен |
| Речь живым голосом | — | BLOCKED — микрофон в сессии давал ~0.002 RMS |
| Звук перевода в колонки | — | UNVERIFIED — проверка шла с громкостью 0 |
| Мост VB-CABLE | — | UNVERIFIED — кабель установлен, включение не прогонялось |
| Хоткей `Alt+CapsLock` (удерживать) | `toggleHotkeys()` | PASS — `live:ptt:down`, отпускание по `GetAsyncKeyState` |
| Входящий канал (loopback) | `reference.wav` → `_on_loopback_pcm`, 48 кГц блоками | PASS — 7 отправок, `peer_text` «ru / Уже хочу есть.» |
| Входящая озвучка | `incoming_speak` → `incoming_chunk` | PASS — чанки получены, отдельный поток наушников открыт |
| Петля на живом прогоне | подача звука во время озвучки | PASS — счётчик отправок не изменился, `speaking=True` |
| Иностранная речь без модели | испанский аудио → `peer_text` | PASS — «нет модели перевода es->ru», без ложного английского |
| Список моделей в UI | запрос `models` после `READY` | PASS — ASR одна, TTS одна, `ru->es` установлен |
| Настройки (спринт) | `peer_lang`, `incoming_volume`, `incoming_on` | PASS — `ui_settings.json` |
| Пакет ES→RU | `snapshot_download` + загрузка модели + 3 фразы | PASS — 594 МБ, переводы верные |
| ES→RU сквозной | испанская фраза → loopback → ASR → MT → TTS | PASS — «Hola, ¿cómo estás?» → «Привет, как дела?», 2 чанка |
| Автоопределение языка | `peer_lang=auto` + испанский клип | PASS — `lang=es`; при уверенности < 0.60 фраза пропускается |
| Автоскачивание пакетов | `setAutoDownload(True/False)` | PASS — состояние доходит до движка и сохраняется |
| Каталог моделей | `{"cmd":"catalog"}` | PASS — 12 моделей, типы ASR/MT/TTS, состояния NOT INSTALLED/STOPPED/READY |
| Выбор ASR | `model_select` | PASS — `model_selected asr=faster-whisper-large-v3-turbo` |
| Проверка целостности | `model_verify es-ru` | PASS — ok, обязательные файлы на месте |
| Отмена загрузки | `model_download` ru-en → `model_cancel` | PASS — DOWNLOADING → CANCELLED, модель не установлена |
| Автозагрузка отсутствующего пакета | английская речь + auto_download | PASS — скачан en-ru (~594 МБ), `package installed`, первая фраза переведена и озвучена |
| Языковые пакеты | `{"cmd":"packs"}` | PASS — 10 пакетов; es READY, en/de/it/fr/zh/hi/ar PARTIAL, pt/ja UNSUPPORTED |
| Автоопределение языка | две английские фразы после испанской | PASS — смена es→en после подтверждения (prob 0.69) |
| Режимы | `mode` fast/quality/balanced | PASS — compute int8→float16, beam 1→3, chunk 20/40/30 |
| Промежуточный ASR | длинная испанская фраза | PASS — 94 `peer_partial`, перевод только финала |
| EN→RU после смены языка | 2 английские фразы | PASS — `peer_lang` es→en, «Good morning…» → «Доброе утро.» |
| Одновременные каналы | RU→ES + ES→RU | PASS — `out_tts` 1205 мс, входящий перевод и озвучка |
| Перезапуск движка | stop → start | PASS — READY → STOPPED → READY |
| Статистика | `cmd: stats` | PASS — RSS 4258 МБ, VRAM 1932 МБ, очередь 0 |
| Нагрузка (короткая) | 5 итераций | PASS — очередь 0–2, dropped 2, без зависаний |
| UI «Настройки» | снимок с режимом и диагностикой | PASS — `shots/settings_modes.png` |
| UI «Модели» | запуск + снимки | PASS — `shots/models_asr.png`, `models_mt.png`, `models_packs.png` |
| Интерфейс после изменений | скриншоты «Перевод» и «Настройки» | PASS — наложений нет, блок моделей помещается |
| Запись образца | `toggleRecording` | UNVERIFIED — старт/стоп работают, сигнала в микрофоне не было |

## Уровень D — Regression (Legacy ↔ новый UI)

Перенесённые функции — в [FEATURE_PARITY.md](FEATURE_PARITY.md).
Не перенесены и требуют решения: массовая озвучка 31 реплики, сборка
серверного ресурса, оверлей субтитров, проверки качества, панель задачи Tk.

Regression-прогон не закрыт: 29 пунктов `UNVERIFIED`/`FAIL`.

## Стабильность: короткий нагрузочный прогон (2026-11-17, 6 минут)

`tools/soak_live.py`: 70 сцен — входящая речь ES/EN с промежуточными срезами,
исходящий перевод (35 сцен, 7 одновременно с входящим), смены режима
fast/quality/balanced, смены языка собеседника es/en/auto, остановка и
повторный запуск движка в середине.

| Показатель | Значение |
|---|---|
| Ошибок Engine | 0 |
| Входящих фраз переведено | 66 из 70 (4 — отказ автоопределения языка) |
| Исходящих переводов завершено | 35 из 35 |
| Очередь собеседника | 0 на всех замерах |
| `dropped` / `cancelled` | 0 / 0 |
| RSS | 5094–5445 МБ (медиана 5351) |
| VRAM | 1902–1980 МБ |
| ASR | p50 97 мс, p95 142 мс, max 179 мс |
| Перевод | p50 51 мс; p95 2139 мс — ленивая загрузка модели при смене языка |
| Первый звук входящего | p50 835 мс, p95 2952 мс, max 4139 мс |
| Первый звук исходящего | p50 1120 мс, p95 1244 мс, max 1364 мс |
| Перезапуск движка | PASS — READY → STOPPED → READY, после старта RSS 4365 МБ |
| Зависания | не обнаружены |

Ограничение: прогон короткий (6 минут). Многочасовой — Roadmap 6.10.

## Промежуточное распознавание (8 фраз: 3 среза + финал)

| Проверка | Результат |
|---|---|
| Промежуточный текст показывается | PASS — 24 среза, непустые |
| Перевод по промежуточным срезам | PASS — 0 переводов до финала |
| Финализация реплики | PASS — 8 из 8 финалов переведены ровно один раз |
| Повтор текста между соседними срезами | 3 из 8 фраз: срез вырос, новых слов ещё нет; текст только для показа |
| Дублирование перевода повторной фразы | не происходит (`_last_translated`) |

## Уровень E — Packaging (2026-11-17)

| Проверка | Результат |
|---|---|
| Сборка `pyinstaller --clean --noconfirm redz_voice_studio.spec` | PASS (≈1,5 мин) |
| Артефакт | `dist/RedZVoiceStudio.exe`, 316 482 741 байт (301,8 МБ), onefile |
| SHA-256 | `b17eaa8c7118970999c210c9331dfa536d906a7058b119aefee92788589c0ba0` |
| Запуск EXE | PASS — окно «Auraloom», `Responding: True`, экран «Модели» отрисован |
| QML внутри бандла | PASS — карточки ASR/MT/TTS, вкладки, статус-бар, боковое меню |
| Остановка движка из EXE | PASS — «Остановить модели» → «[engine] модели выгружены (RSS=1678 МБ)» |
| Повторный запуск движка | PASS — «Движок: Готов к работе», RTX 5080, VRAM 5,7/16 ГБ |
| Остальные экраны в EXE | ЧАСТИЧНО — «Главная» открыта; остальные сверены в том же QML (`test_launch.py`, скриншоты) |
| Qt внутри бандла | PASS — загружены `Qt6Quick.dll`, `Qt6Qml.dll`, `Qt6QuickEffects.dll` |
| Чистое окружение | UNVERIFIED — проверялось на машине разработчика |
| Движок в бандле | N/A — по архитектуре внешний (`engine/`) |

## Obsidian (read-only)

| Шаг | Результат |
|---|---|
| Обнаружен vault | `C:\Users\cyril\Documents\Obsidian\HermesVault\HermesVault` (из `obsidian.json`) |
| Проектные заметки | 8 файлов в `80-Память/10-Проекты/RedZ-Voice-Studio` |
| Чтение | PASS — README, 00-СОСТОЯНИЕ, 01-АРХИТЕКТУРА, 06-РАБОЧИЙ-КОНТЕКСТ, заголовки 02/03/04 |
| Изменения в vault | не вносились |
| MCP | BLOCKED — в текущей сессии Freebuff нет MCP-инструментов; подключение выполнено файловым read-only доступом |

## Команды быстрой проверки перед коммитом

```bash
python -m compileall -q app
python -m unittest discover -s tests -q
"C:/Users/cyril/AppData/Roaming/Python/Python314/Scripts/pyside6-qmllint.exe" \
  -I app/qtapp/qml app/qtapp/qml/main.qml app/qtapp/qml/pages/*.qml app/qtapp/qml/RedZ/*.qml
python app/qtapp/test_launch.py     # QML грузится и окно создаётся
python tools/soak_live.py --minutes 6   # нагрузочный прогон движка
python tools/probe_partial.py           # промежуточное распознавание
python -m unittest tests.test_peer_incoming_qt -v   # обратный перевод
```

Runtime-проверки движка (долгие, 20–60 с каждая) выполняются вручную:
запуск/остановка/крах/перезапуск и прогон аудиофайла через пайплайн.
