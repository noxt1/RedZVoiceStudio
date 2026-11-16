# ARCHITECTURE — RedZ Voice Studio

Только подтверждённое кодом и запуском. Проверено 2026-11-16.

## 1. Общая схема

```
┌──────────────────────────── GUI (Python 3.14) ────────────────────────────┐
│  PySide6 6.12 + QML/Qt Quick                                              │
│  app/qtapp/qml/main.qml ─ Loader ─ pages/{Home,Voices,Settings,History,   │
│                                              Phrases}.qml                │
│  дизайн-система: RedZ/{Theme, Card, Glow, AppButton, AppCombo, AppSwitch, │
│                  AppField, AppSlider, Icon, PageTitle, StatusPill, Toast} │
│                                                                           │
│  контекст QML: appState, liveEngine, voiceController, promptModel,        │
│                takeModel, sampleModel, historyModel                       │
└───────────────┬───────────────────────────────┬───────────────────────────┘
                │ вызовы слотов/свойств          │ сигналы (notify)
                ▼                                ▼
     AppState (app_state.py)            LiveEngine (live_engine.py)
     настройки, устройства, фразы,      PTT, непрерывный режим, уровень,
     VRAM, хоткеи, мост, профили        очередь фраз, состояние движка
                │                                │
                │                    LiveTranslator (live_client.py)
                │                                │ JSON-lines: stdin/stdout
                ▼                                ▼
     app/*.py: studio_paths, studio_core,     engine/python.exe
     mic_bridge, cable, hotkeys, translate,   tools/live_translate.py
     wasapi_loopback, incoming_tts            faster-whisper + opus-mt + XTTS
```

Тяжёлый стек в GUI не импортируется: `torch`, `TTS`, `transformers` исключены
из PyInstaller-сборки (см. `app/redz_voice_studio.spec`, `excludes`).

## 2. Слои

| Слой | Модули | Ответственность |
|---|---|---|
| UI | `app/qtapp/qml/**` | отрисовка, ввод, навигация, тосты; никакой бизнес-логики |
| Presentation-мост | `app/qtapp/app_state.py`, `live_engine.py`, `voice_controller.py`, `models.py` | свойства/слоты/сигналы для QML, состояния, валидация |
| Ядро | `studio_core.py`, `studio_paths.py`, `prompt_library.py`, `voice_prompts.py` | запись, reference, раскладка файлов, профили, подсказки |
| Аудио | `mic_bridge.py`, `wasapi_loopback.py`, `incoming_tts.py`, `cable.py`, `audiodev.py`, `acoustic.py` | устройства, маршрутизация, захват, установка кабеля |
| Интеграции | `live_client.py`, `translate.py`, `hotkeys.py` | IPC движка, текстовый перевод, глобальные клавиши |
| Legacy UI | `voice_studio.py`, `ui/**` | старый Tk-интерфейс (3 и 6 вкладок), сохранён |

## 3. IPC с движком

`LiveTranslator` запускает `engine_python tools/live_translate.py --reference=<wav>`
и общается строками JSON.

**GUI → движок**

| Команда | Параметры | Назначение |
|---|---|---|
| `load` | — | загрузить ASR + перевод + XTTS |
| `lang` | `code` | язык перевода (es/en/ow/it) |
| `peer_lang` | `code` | язык речи собеседника (`auto`/es/en/it/ru) |
| `liveliness` | `level` 0–3 | выразительность синтеза |
| `translate` | `seq`, `sr`, `pcm` (int16) | перевести фрагмент речи |
| `peer` | `sr`, `pcm` | распознать/перевести чужую речь |
| `incoming_speak` | `text`, `lang` | озвучить входящий перевод |
| `speak` | `text` | озвучить текст (звуковая панель) |
| `unload` | — | выгрузить модели (RAM) |
| `quit` | — | завершить процесс |
| `mode` | `code` | Fast/Balanced/Quality/Manual |
| `stats` | — | RAM/VRAM, очереди, счётчики |
| `catalog` | — | каталог моделей и состояние |
| `packs`, `pack_install`, `pack_remove`, `pack_verify` | `code` | языковые пакеты |
| `peer` | `sr`, `pcm`, `partial` | фраза собеседника (partial — только показ) |

**Движок → GUI (`event`)**

`boot`, `ready`, `state` (`{"ready":true}` или `{"error":…}`), `text`,
`peer_text`, `lang`, `peer_lang`, `chunk`, `done`, `incoming_chunk`,
`incoming_done`, `unloaded`, `error`, `mode`, `peer_partial`, `metrics`,
`stats`, `catalog`, `download`, `packs`, `pack`. stderr построчно идёт в
`workspace/logs/live_engine_stderr.log` и в `on_event("log", …)`.

**Поколение процесса.** `LiveTranslator` тегирует строки выводом номером
процесса (`_proc_gen`): остаток вывода старого движка после перезапуска
игнорируется и не опрокидывает новый движок в `ERROR`.

## 3.1. Режимы работы

| Режим | ASR | compute | beam | TTS chunk | проверки синтеза |
|---|---|---|---|---|---|
| Fast | самая быстрая установленная | int8_float16 | 1 | 20 | 0 |
| Balanced | самая качественная установленная | int8_float16 | 1 | 30 | 1 |
| Quality | самая качественная | float16 | 3 | 40 | 2 |
| Manual | выбор пользователя | из последнего режима | | | |

Режим никогда не скачивает модели: если вариант один, `mode_info`
показывает `asr_alternatives = 1`. Перевод выбирается языком/направлением,
а не режимом.

## 3.2. Очереди, guards и метрики

- Очередь собеседника ограничена (8): при переполнении сначала вытесняются
  промежуточные срезы, счётчик `dropped` растёт.
- Исходящая очередь ограничена 3 фразами, старая фраза вытесняется.
- `Engine.gen` растёт при смене языка/режима/модели; результат с устаревшим
  поколением отбрасывается (`cancelled`).
- Входящие аудиочанки с чужим `seq` не воспроизводятся (проверка на стороне UI).
- Метрики (`metrics`, `stats`) пишутся в `workspace/logs/diagnostics.log`;
  в интерфейсе — блок «Диагностика» в Настройках.

## 4. Состояния движка

```
STOPPED ──start──► LOADING ──ready──► READY ──stop──► STOPPING ──► STOPPED
                      │                 │
                      └──── error ──────┴──► ERROR ──start──► LOADING
```

- Источник истины — `LiveEngine._state`; в UI он попадает через
  `AppState.syncEngineState` (связывается в `LiveEngine.attach`).
- `WARMING UP` отдельным состоянием **не выделен**: прогрев моделей происходит
  внутри `LOADING` до события `ready` (см. FEATURE_PARITY, п. «прогрев»).
- Ошибки: `LiveEngine._set_state("ERROR", msg)` → тост + текст в карточке.
- Смерть процесса движка: EOF в stdout → ошибка «движок остановился»,
  `proc = None`, состояние `ERROR`; следующий `start()` поднимает процесс заново.
- `stop()` отправляет `unload` и `quit` **до** завершения процесса, затем
  `terminate()` (8 с) / `kill()`.

## 5. Потоки и таймеры

| Место | Поток | Что делает |
|---|---|---|
| `LiveTranslator._read_loop/_read_err` | фоновые потоки | читают stdout/stderr движка в очередь |
| `LiveTranslator.poll()` | GUI-поток по `QTimer` 100 мс | разбирает очередь событий |
| `LiveEngine._poll_timer` | GUI | `translator.poll()` |
| `LiveEngine._level_timer` | GUI | 100 мс, публикует уровень микрофона |
| `LiveEngine._hold_timer` | GUI | 50 мс, ожидание конца воспроизведения для ducking |
| аудиоколбэки (`_cont_callback`, `MicBridge`) | PortAudio | копят/микшируют звук, обновляют уровень |
| `AppState._poll_timer` | GUI | очередь хоткеев (50 мс) |
| `AppState._vram_timer` | GUI | `nvidia-smi` раз в 4 с |

Очередь перевода: `self._queue` + `_queue_lock`, отправка по одной
(`translator.busy`), длинная фраза режется по 14 с (MAX_SEG).

## 6. Аудио

- Частоты: запись/микрофон 48 кГц (`SR_REC`), ASR 16 кГц (`SR_ASR`),
  TTS 24 кГц (`SR_TTS`), мастер 44.1 кГц. Ресемплинг — линейная интерполяция
  numpy (scipy в EXE отсутствует).
- `MicBridge`: вход микрофона + очередь фраз + очередь TTS → одно устройство
  вывода; `mic_gain`, `monitor_gain`, ducking, `play_phrase`, `push_pcm`,
  `push_incoming_pcm`.
- `LoopbackCapture` (WASAPI): захват системного звука для речи собеседников,
  режимы и статусы через enum.
- `IncomingTTSProvider`: входящий перевод озвучивается в наушники, чтобы не
  попасть обратно в микрофон.

## 7. Данные и конфигурация

| Что | Где |
|---|---|
| workspace | `%LOCALAPPDATA%\RedZVoiceStudio\workspace` (сидинг из ресурсов при старте) |
| движок | `%LOCALAPPDATA%\RedZVoiceStudio\engine` (venv 3.12, ставится `tools/setup_env.ps1`) |
| настройки UI | `workspace/ui_settings.json` |
| свои фразы | `workspace/custom_phrases.json` |
| профили голоса | `workspace/profiles/<name>/` + активный профиль |
| логи | `workspace/logs/` |
| однократный запуск | `app.lock` (`studio_paths.single_instance_lock`) |

## 8. Запуск приложения

1. `app/voice_studio.py` → выбор UI: `--ui-old`, `--ui-new`, иначе Qt (если
   PySide6 импортируется).
2. `qtapp.main`: `QGuiApplication` → `AppState`, `LiveEngine`, `VoiceController`,
   модели → контекст QML → `engine.addImportPath(qml)` → `main.qml`.
3. `state.refreshDevices()`, `state.refreshPhrases()`.
4. Автозапуск движка — только если включена настройка и движок установлен.
5. Модели **никогда** не грузятся без действия пользователя (кроме этой
   настройки, выключенной по умолчанию).

## 9. Сборка

`app/redz_voice_studio.spec`: entry `app/voice_studio.py`; данные — `lines.json`,
`player/`, `voices/`, `tools/`, `installers/`, Lua-ресурс, `html/`,
`app/qtapp/qml → qtapp/qml`, `studio.ico`; hiddenimports — модули ядра, `ui.*`,
`qtapp.*`, `PySide6.QtCore/QtGui/QtQml/QtQuick/QtSvg`. Итог:
`dist/RedZVoiceStudio.exe` (onefile, ~316 МБ). QML-модули QtQuick собираются
хуком `hook-PySide6.QtQml` (проверено: в запущенном EXE загружены
`Qt6Quick.dll`, `Qt6Qml.dll`, `Qt6QuickEffects.dll`).

## 10. Обработка ошибок и устойчивость

- Ошибки движка → состояние `ERROR` + тост; повторный запуск разрешён.
- Падение процесса движка определяется по EOF и по `proc.poll()` в `start()`,
  поэтому «залипший» процесс не блокирует перезапуск.
- Исключения GUI пишутся в `workspace/logs/gui_crash.log` (перехват в
  `voice_studio.py`); туда же попали Qt-слоты.
- Все слоты `AppState` проверяют `None` для моста/движка.
- Загрузка настроек/фраз обёрнута в `try` — битый JSON не роняет приложение.
