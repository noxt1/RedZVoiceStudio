# tools/ — что чем проверять

Индекс CLI-инструментов Auraloom: 150 `.py` и один `setup_env.ps1`.
Часть папки — не «утилиты разработчика», а **работающий код продукта**: движок
живого перевода и модули, которые он импортирует. Поэтому папка целиком
попадает в EXE (см. `app/redz_voice_studio.spec`) и копируется в рабочую папку
(`studio_paths.workspace_tools()`).

## Каким интерпретатором запускать

| Интерпретатор | Что им запускать |
|---|---|
| системный `python` (3.14, PySide6, numpy, sounddevice, soundfile) | скриншоты, навигация, устройства, проверка файлов, `selftest.py` |
| движок `%LOCALAPPDATA%\Auraloom\engine\Scripts\python.exe` (3.12 + torch/transformers/TTS) | `live_translate.py`, `xtts_clone.py`, `synthesize.py`, `voice_*.py`, `quality_sweep.py`, `glossary.py`, `model_*.py`, `download_model.py`, `diagnose_*.py` |
| собранный `dist/RedZVoiceStudio.exe` | `click_voice_all.py`, `test_hotkey_e2e.py`, `test_live_ui.py` |

## 1. Рантайм: зовётся из приложения или движка — не перемещать

| Файл | Что делает | Кто использует |
|---|---|---|
| `live_translate.py` | движок живого перевода: модели в памяти, IPC построчным JSON | `app/qtapp/live_engine.py`, `app/live_client.py` |
| `voice_lang.py` | языки речи/озвучки, пакеты моделей | `app/studio_core.py` (`tool_path`), движок |
| `western_style.py` | Old West — стиль английского, не отдельный язык | `voice_lang.py`, `app/studio_core.py` |
| `xtts_clone.py` | клон голоса XTTS-v2, сборка reference | `app/studio_core.py`, движок |
| `voice_post.py` | пост-обработка живости (интонация, паузы, темп) | `live_translate.py` |
| `voice_tone.py` | темп и тон по смыслу фразы | `live_translate.py`, `xtts_clone.py` |
| `prosody.py` | разброс F0 — объективный критерий «плоской» речи | `xtts_clone.py`, `measure_prosody.py` |
| `audio_post.py` | общая нормализация/лимитер | `xtts_clone.py`, `synthesize.py` |
| `glossary.py` | глоссарий имён и терминов для MT | `live_translate.py` |
| `model_registry.py` | каталог моделей — единый источник правды | `live_translate.py`, `model_discovery.py` |
| `model_discovery.py` | обновляемый каталог с HuggingFace | `live_translate.py`, `model_registry.py` |
| `download_model.py` | загрузка одной модели отдельным процессом (прогресс/отмена) | `live_translate.py` |
| `synthesize.py` | массовая озвучка (Piper и XTTS) | `app/studio_core.py`, `app/voice_prompts.py`, `build_prompt_audio.py` |
| `voice_similarity.py` | метрика похожести клона на образец | `app/studio_core.py`, `selftest.py`, `voice_scanner.py` |
| `check_quality.py` | транскрипция клипов через Whisper | `app/studio_core.py` |
| `check_rules.py` | реплики против правил RedZ (п. 3.2) | `app/studio_core.py` |
| `check_sync.py` | синхронность `lines.json` ↔ плеер ↔ hotkeys | `app/studio_core.py` |
| `setup_env.ps1` | venv движка (torch + coqui-tts) | первый запуск, документация |
| `megrel_style.py` | грузинский → мегрельский | **нигде не импортируется** — либо подключить, либо в archive |

## 2. Установка, окружение, железо

| Скрипт | Назначение |
|---|---|
| `selftest.py` | главный чек-лист установки: рабочая папка, движок, голоса, модели, устройства; `--full` добавляет замер похожести |
| `check_vram.py` | реальное состояние VRAM через CUDA |
| `check_xtts.py` | видит ли движок веса XTTS-v2 |
| `diag_devices.py` | индексы аудиоустройств (запомненный микрофон мог съехать) |
| `probe_devices.py` | честная проверка: какие устройства реально открываются с чтением/записью |
| `check_cable_installed.py` | появились ли устройства VB-CABLE после установки |
| `find_cable_installer.py` | откуда взять установщик кабеля, когда vb-audio.com недоступен |
| `fetch_xtts.py` | скачать XTTS-v2 пофайлово (когда `snapshot_download` не тянет LFS-блоки) |
| `find_record_mic.py` | найти индекс микрофона, которым реально записывались подсказки (Fifine виден несколько раз) |
| `check_cable_sources.py`, `find_cable_mirrors.py` | поиск зеркал установщика (кандидаты в archive) |
| `click_installer.py` | нажать кнопку в окне установщика VB-CABLE (автоматизация установки) |
| `check_encoding.py` | какие символы испанского не кодируются в cp1251 |
| `check_legacy.py` | Legacy Tk UI: шесть вкладок не сломаны |
| `check_new_ui.py` | интеграция Qt-интерфейса с `LiveTab` |

## 3. Замеры: задержка, нагрузка, качество перевода

| Скрипт | Назначение |
|---|---|
| `bench_swap_latency.py` | реальная задержка перевода: от отправки аудио до первого звука (349–425 мс в README) |
| `test_swap_latency.py` | хоткей доходит до интерфейса + переводится только последняя фраза |
| `soak_live.py` | длинный прогон (`--minutes N`): стабильность, очереди, память; p50 задержки первого звука |
| `probe_partial.py` | промежуточное распознавание: три растущих среза и финал, без дублей |
| `quality_sweep.py` | качество: варианты декодирования MT и настройки XTTS (chrF/WER) |
| `test_langs.py` | перевод на разные языки + перехват речи игроков |
| `calibrate_similarity.py` | калибровка метрики похожести (различает ли она голоса) |
| `clone_matrix_test.py` | матрица «референс × клон»: решающий тест клонирования |
| `ab_reference.py` | A/B старого и нового образца голоса |
| `compare_expressiveness.py` | сравнение наборов с разной «живостью» интонации |
| `measure_prosody.py` | разброс F0 и энергии по репликам |
| `measure_own_voice.py` | эталон «настоящий голос» из сырых записей против клона |
| `check_resample_quality.py` | влияние алиасинга ресемплинга на оценку похожести |
| `check_prompt_audio.py` | готовые подсказки: уровни, длительности, целостность |

## 4. Голос: референс и звуковые подсказки

| Скрипт | Назначение |
|---|---|
| `record_reference.py` | записать 15–25 с своего голоса для клонирования |
| `voice_scanner.py` | интерактивный сканер голоса (кнопка → подсказки → запись → оценка) |
| `build_prompt_audio.py` | заранее озвучить подсказки в `voices/prompts/`, чтобы образец звучал мгновенно |
| `debug_prompt_audio.py` | что именно ломается в озвучке подсказок |
| `optimize_tempo.py`, `fix_shorts.py` | подбор `length_scale` для плохо распознаваемых выкриков; пишут `length_scales.json` |
| `pick_phrasing.py` | подбор устойчивых формулировок, которые XTTS произносит стабильно |
| `voice_everything.py` | озвучить все фразы панели голосом пользователя (то же, что кнопка; в Qt-интерфейсе экрана нет) |

## 5. Интерфейс: скриншоты и навигация

| Скрипт | Назначение |
|---|---|
| `shot.py` | скриншот окна Auraloom (вёрстка); `python tools/shot.py out.png` |
| `shot_qt.py` | снимок QML через `QQuickWidget` без показа окна |
| `shot_scrolled.py` | снимок вкладки с прокруткой (позиция 0..1) |
| `history_shot.py` | «История» с четырьмя репликами (не пишет в настоящую историю) |
| `nav_key_check.py` | `Tab` → `Down` ×2 → `Enter` меняет раздел (QTest, offscreen) |
| `test_qml_render.py` | рендер QML в offscreen через `QQuickRenderControl` |
| `check_shot.py` | проверка скриншота без человека: непустые пиксели, число цветов, полосы |
| `diag_pages.py` | что реально отрисовано на каждой странице |
| `shot_pages.py`, `shot_voices.py` | скриншоты страниц/под-вкладок (импортируют `tkinter` ради DPI — проверять, что снимают Qt-окна) |
| `switch_tab.py`, `view_tab.py` | переключить вкладку и снять скриншот (эпоха Tk) |

## 6. Аудио, микрофон, хоткеи — разбор дефектов

| Скрипт | Назначение |
|---|---|
| `probe_mic.py` | микрофон без голоса: уровень и каналы |
| `check_bridge.py` | авто-маршрут под кабель: мост реально стартует |
| `test_mic_bridge.py` | сигнал проходит микрофон → выход |
| `test_bridge_with_mic.py` | мост с конкретным (запомненным) микрофоном |
| `test_hold_button.py` | режим «ЗАЖАТЬ»: русский пропадает, отпустил — вернулся |
| `test_stereo_mix.py` | ловит ли «Стерео микшер» то, что идёт в наушники |
| `probe_capture.py` | какое устройство записи слышит системный звук |
| `test_peer_capture.py` | сквозной перехват речи игроков (испанская реплика → loopback) |
| `test_acoustic.py` | акустический режим: фраза в динамики → микрофон её слышит |
| `probe_hotkey.py`, `probe_hotkey2.py`, `probe_peek.py` | доходит ли `WM_HOTKEY` при синтетическом вводе (`keybd_event` vs `SendInput`) |
| `test_hotkey_dispatch.py` | хоткей доходит до обработчика интерфейса |
| `test_hotkeys.py` | глобальные хоткеи живого перевода |
| `test_hotkey_e2e.py` | хоткеи в собранном EXE |
| `test_continuous.py`, `test_cont_flow.py` | непрерывный режим без микрофона: нарезка по паузам, подмена потока |
| `test_interactions.py` | реальные нажатия: PTT, mute, громкость, история |
| `test_phrase_flow.py`, `test_studio_logic.py` | логика без GUI: фразы, перевод, payload |
| `test_tempo.py` | темп и паузы (C.7.7) |
| `test_clone_new_ui.py` | клонирование в новом UI без запуска нейросети |
| `test_live_src.py`, `test_live_ui.py`, `test_gui_flow.py`, `test_c72_features.py`, `test_c73_features.py`, `test_tree_style.py` | сценарии Tk-эпохи (две громкости моста, лимитер, фон ttk.Treeview) — под вопросом |

## 7. Оверлей субтитров

| Скрипт | Назначение |
|---|---|
| `overlay_win.py` | оверлей поверх игры, чистый Win32/GDI (в Qt-интерфейсе экрана нет — FAIL в FEATURE_PARITY) |
| `check_overlay_integration.py` | галочка → процесс → файл |
| `check_overlay_two.py` | две строки: своя речь и речь игроков |
| `diag_overlay.py` | окно поверх всех? текст виден? (по пикселям) |

## 8. Обслуживание проекта

| Скрипт | Назначение |
|---|---|
| `pack_zip.py` | архив проекта в обход блокировки занятого EXE |
| `gen_icons.py` | SVG-иконки RedZ 24×24 в едином стиле |
| `sync_assets.py`, `sync_player.py` | перегенерировать `keybinds.lua` / `player/index.html` из `lines.json` |
| `fix_structure.py` | починить структуру `lines.json` и регекс плеера |
| `check_vault.py`, `link_vault_index.py` | стек памяти в Obsidian: целостность и индекс |
| `click_voice_all.py` | автоматизация: запустить EXE и нажать «Озвучить всё моим голосом» |

## 9. `archive/` — перенесено 2026-11-19

Перенесено `git mv` (история сохранена), ничего не удалено: файлы остаются
в репозитории, но больше не едут в EXE и в рабочую папку. Осталось
на месте 106 скриптов, в `archive/` — 44.

Скрипты в `archive/` считают корень проекта как `dirname(dirname(__file__))`,
то есть рассчитаны на запуск из `tools/`. Если какой-то из них понадобится
снова — `git mv tools/archive/<файл> tools/`, а не запуск на месте.

### A. Одноразовые патчи кода (17) — в `archive/`; повторный запуск испортит файлы

`patch_bridge_mic.py`, `patch_bridge_rate.py`, `patch_button_steps.py`,
`patch_clean_progress.py`, `patch_diag_button.py`, `patch_expressiveness.py`,
`patch_expressiveness_ui.py`, `patch_guide.py`, `patch_job_robust.py`,
`patch_job_steps.py`, `patch_mic_pick.py`, `patch_panel_heartbeat.py`,
`patch_prosody_numpy.py`, `patch_rates.py`, `patch_remember_mic.py`,
`patch_stall_report.py`, `patch_task_panel.py`.

Обоснование: 13 из 17 правят Legacy Tk (`app/voice_studio.py`, `app/logpanel.py`)
текстовыми заменами. Правки уже в коде; скрипт, запущенный второй раз,
ищет старый фрагмент и либо падает, либо портит файл.

### B. Диагностика закрытых дефектов (19 из 21 `diag_*`) — в `archive/`

`diag_acoustic.py`, `diag_acoustic2.py`, `diag_analyze_take.py`,
`diag_best_rate.py`, `diag_compare_rates.py`, `diag_default_device.py`,
`diag_exact_rate.py`, `diag_hold.py`, `diag_hotkey_race.py`,
`diag_mic_combo.py`, `diag_mic_rate.py`, `diag_mic_read.py`,
`diag_overlay.py`, `diag_pages.py`, `diag_record_fixed.py`,
`diag_record_once.py`, `diag_record_rate.py`, `diag_stream_rate.py`,
`diag_take_content.py`.

Обоснование: каждый отвечал на один вопрос («почему 9449 отсчётов в секунду»,
«почему писк в дубле», «почему хоткей теряется на старте потока»). Ответы
записаны в README и CHANGELOG, баги закрыты.
**Остаются на месте:** `diag_devices.py` (индексы устройств меняются),
`diag_vad_level.py` (порог VAD под конкретный микрофон).

### C. Репро и исследования (8) — в `archive/`

`repro_frozen.py`, `repro_gui.py`, `repro_voice_all.py` — воспроизводили
`PermissionError` в «Озвучить всё», баг закрыт.
`diagnose_clip_duration.py`, `diagnose_clone_identity.py`,
`diagnose_intelligibility.py`, `diagnose_postprocess.py`, `diagnose_xtts.py` —
исследования качества XTTS; выводы уже в доках и в настройках `xtts_clone.py`.

### D. Осталось на месте — решать отдельно (7)

`find_cable_mirrors.py`, `check_cable_sources.py` — обход недоступного
vb-audio.com (пригодится на чужой машине); `click_installer.py` —
автоматизация установщика; `megrel_style.py` — не подключён ниоткуда;
`test_live_src.py`, `test_live_ui.py`, `test_gui_flow.py`, `test_c72_features.py`,
`test_c73_features.py`, `test_tree_style.py` — сценарии Tk-эпохи.

### Что учтено при переносе

1. `studio_paths.workspace_tools()` читает `tools/` **без рекурсии** — файлы
   из `archive/` перестанут копироваться в рабочую папку (это и нужно).
2. `app/redz_voice_studio.spec` обходит папку через `os.walk` **рекурсивно**,
   поэтому `archive` добавлен в фильтр `dirnames` — иначе архив уехал бы в EXE.
3. Документация ссылается на 20+ имён из `tools/` (`live_translate`,
   `glossary`, `model_registry`, `model_discovery`, `download_model`,
   `voice_tone`, `voice_post`, `prosody`, `xtts_clone`, `quality_sweep`,
   `soak_live`, `probe_partial`, `bench_swap_latency`, `nav_key_check`,
   `history_shot`, `build_prompt_audio`, `check_prompt_audio`,
   `overlay_win`, `voice_everything`, `setup_env.ps1`) — все они остаются
   на своих местах.
4. После переноса имеет смысл прогнать `python tools/selftest.py` и один
   `soak_live.py --minutes 2`, чтобы убедиться, что движок не искал
   перемещённые файлы.

## 10. Правило для новых скриптов

Новый файл в `tools/` появляется только вместе со строкой в этом индексе:
назначение, чем запускать (системный python / python движка / EXE) и на какой
вопрос он отвечает. Скрипт, который правит код текстовыми заменами, живёт
сразу в `tools/archive/` — в продуктовую папку он не попадает.
