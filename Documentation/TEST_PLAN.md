# TEST_PLAN — RedZ Voice Studio

Уровни проверок A–E. Для каждого — команда и фактический результат на
2026-11-16 (Windows, Python 3.14, PySide6 6.12, `main` @ `9fc19e4` + рабочая
директория).

Окружение: `QT_QPA_PLATFORM=windows` для визуальных проверок (offscreen даёт
«тофу» вместо шрифтов), `offscreen` — для логических.

## Уровень A — Static

| Проверка | Команда | Результат |
|---|---|---|
| Компиляция Python | `python -m compileall -q app` | PASS (без ошибок) |
| Юнит-тесты | `python -m unittest discover -s tests -q` | PASS — 78 тестов (было 62; +16 в `test_peer_incoming_qt.py`) |
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
| Хоткей `Ctrl+Alt+L` | `toggleHotkeys()` | PASS — регистрация `live:cont`, снятие чистое |
| Входящий канал (loopback) | `reference.wav` → `_on_loopback_pcm`, 48 кГц блоками | PASS — 7 отправок, `peer_text` «ru / Уже хочу есть.» |
| Входящая озвучка | `incoming_speak` → `incoming_chunk` | PASS — чанки получены, отдельный поток наушников открыт |
| Петля на живом прогоне | подача звука во время озвучки | PASS — счётчик отправок не изменился, `speaking=True` |
| Иностранная речь без модели | испанский аудио → `peer_text` | PASS — «нет модели перевода es->ru», без ложного английского |
| Список моделей в UI | запрос `models` после `READY` | PASS — ASR одна, TTS одна, `ru->es` установлен |
| Настройки (спринт) | `peer_lang`, `incoming_volume`, `incoming_on` | PASS — `ui_settings.json` |
| Интерфейс после изменений | скриншоты «Перевод» и «Настройки» | PASS — наложений нет, блок моделей помещается |
| Запись образца | `toggleRecording` | UNVERIFIED — старт/стоп работают, сигнала в микрофоне не было |

## Уровень D — Regression (Legacy ↔ новый UI)

Перенесённые функции — в [FEATURE_PARITY.md](FEATURE_PARITY.md).
Не перенесены и требуют решения: массовая озвучка 31 реплики, сборка
серверного ресурса, оверлей субтитров, проверки качества, панель задачи Tk.

Regression-прогон не закрыт: 29 пунктов `UNVERIFIED`/`FAIL`.

## Уровень E — Packaging

| Проверка | Результат |
|---|---|
| Сборка `pyinstaller --clean --noconfirm redz_voice_studio.spec` | PASS (≈2.5 мин) |
| Артефакт | `dist/RedZVoiceStudio.exe`, 316 МБ, onefile |
| Запуск EXE | PASS — окно «RedZ Voice Studio», `Responding: True` |
| Qt внутри бандла | PASS — загружены `Qt6Quick.dll`, `Qt6Qml.dll`, `Qt6QuickEffects.dll` |
| QML внутри бандла | PASS — интерфейс отрисован (проверено по модулям и окну) |
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
python -m unittest tests.test_peer_incoming_qt -v   # обратный перевод
```

Runtime-проверки движка (долгие, 20–60 с каждая) выполняются вручную:
запуск/остановка/крах/перезапуск и прогон аудиофайла через пайплайн.
