# Аудит проекта RedZ Voice Studio

Дата: 15.11.2026
Состояние: рабочая база (Legacy) + незавершённый порт на PySide6/QML

---

## 1. Что работает сейчас

| Компонент | Состояние | Проверка |
|---|---|---|
| Legacy UI (Tkinter, 6 вкладок) | рабочий | флаг `--ui-old` |
| Новый Tk-UI (3 раздела) | рабочий | режим по умолчанию |
| Тесты | 62/62 OK | `python -m unittest discover -s tests` |
| Сборка EXE | есть | `dist/RedZVoiceStudio.exe` (173 МБ, 14.11 19:33) |
| Движок (Whisper/opus-mt/XTTS) | отдельный процесс | не тронут, не дублируется |

Точки входа:

```
python app/voice_studio.py             # новый Tk-UI (по умолчанию)
python app/voice_studio.py --ui-old    # Legacy
python app/voice_studio.py --ui-qt     # Qt/QML (в разработке)
```

---

## 2. Найденные и исправленные баги

### 2.1 Критический: сломанный отступ в `main()` (ИСПРАВЛЕНО)

`app/voice_studio.py`, строка ~2488. После блока `if ui_mode == "qt":` тело
ветки «новый Tk-UI» было с отступом 8 пробелов вместо 4. Python принимал это
как вложенный блок внутри `if ui_mode == "qt"` — то есть **новый интерфейс
никогда не запускался**, при `--ui-qt` или без флага приложение молча падало.

Исправлено: блок возвращён на уровень функции. 62 теста проходят, структура
`main()` проверена через AST (10 If-узлов, все ветки корректны).

### 2.2 Qt/QML не попадает в сборку (НЕ ИСПРАВЛЕНО)

`app/redz_voice_studio_qa.spec` не содержит ни `PySide6`, ни `qtapp`, ни
QML-ресурсов. Даже рабочий Qt-интерфейс в EXE не соберётся.

### 2.3 QML-предупреждения (ИСПРАВЛЕНО)

- `letterSpacing` → `font.letterSpacing` (6 файлов)
- `StatusPill.state` конфликтовал с `QQuickItem.state` → `pillState`
- `FlatBorder.width/radius` → `borderWidth/cornerRadius`
- `AppSlider.valueChanged` дублировал встроенный сигнал → `moved`
- `AppField.focus()` затенял `focus` → `setFocus()`
- `LangCombo` использовал `Popup.popup.visible` (не существует) → свойство `dropdownOpen`
- `StepProgress` использовал несуществующий тип `Circle` → `Rectangle`
- `Theme.warningDeep` без типа → `color`
- `Divider` не имел свойства `color` (использовалось в `main.qml`)

Итог: `pyside6-qmllint` по всем 31 QML-файлу — без предупреждений.

### 2.4 Дубли кода в QML

- `HomePage.qml` — дублирует `LivePage.qml`, но не подключён к `main.qml`
- `shot_main.qml` — тестовая копия `main.qml` (корень `Item` вместо `Window`),
  нужна только для скриншотов

---

## 3. Порт на PySide6/QML: что сделано

### 3.1 Python-слой (`app/qtapp/`)

| Файл | Назначение | Состояние |
|---|---|---|
| `main.py` | точка входа Qt, регистрация QML-контекста | рабочий |
| `app_state.py` | устройства, мост, хоткеи, статус движка | рабочий |
| `live_engine.py` | headless PTT/непрерывный/захват/TTS | рабочий |
| `voice_controller.py` | запись дублей, подсказки, сравнение, reference | рабочий |
| `models.py` | 4 × QAbstractListModel для QML | рабочий |
| `test_launch.py` | smoke-тест запуска | рабочий |
| `diag_qml.py` | диагностика загрузки QML | рабочий |

Движок не дублируется: используются `live_client.LiveTranslator`,
`mic_bridge.MicBridge`, `studio_core.Recorder`, `wasapi_loopback`.

### 3.2 QML-слой

Компоненты (`qml/RedZ/`): `Theme`, `AppButton`, `AppIconButton`, `AppSwitch`,
`AppSlider`, `AppCombo`, `AppField`, `AppTab`, `AppTabs`, `LangCombo`,
`LevelMeter`, `StatusPill`, `Panel`, `WaveformVisualizer`, `StepProgress`,
`Divider`, `Icon`, `FlatBorder`, `Toast`, `qmldir`. 31 SVG-иконка.

Страницы (`qml/pages/`): `LivePage`, `VoicesPage`, `SettingsPage`,
`HistoryPage`, `HomePage` (не подключена).

### 3.3 Что подключено к QML (проверено grep)

44 обращения к `appState.*`, `liveEngine.*`, `voiceController.*`,
`historyModel.*`. Среди них: `startEngine`, `toggleBridge`, `autoRoute`,
`setInDevice/OutDevice`, `refreshDevices`, `cableStatus`, `pressToTalk`,
`releaseToTalk`, `setContinuous`, `startCapture`, `setLang`, `setLiveliness`,
`toggleRecording`, `compare`, `buildReference`, `playPromptAt`, `deleteSample`.

### 3.4 Чего нет

- `promptModel`, `takeModel`, `sampleModel` зарегистрированы, но в QML не используются
- Табы `Connect`, `Soundboard`, `System` в `main.qml` без страниц (последний ведёт на `HistoryPage`)
- Нет истории переводов в реальном времени (модель есть, UI частично)
- Нет вкладки «Настройки» с устройствами/кабелем/хоткеями полностью
- Нет оверлея, микшера, горячих клавиш фраз в Qt-версии

---

## 4. Ограничения окружения

- **Скриншоты нечитаемы**: `QQuickWidget.grabFramebuffer()` и
  `QQuickWindow.grabWindow()` в этой среде отдают белый кадр (98.6% белого,
  1.0% тёмного). Нет реального дисплея/GPU-контекста.
  Проверено: `QT_QPA_PLATFORM=windows`, `offscreen`, `QQuickRenderControl`
  с `QOpenGLContext` — контекст не создаётся.
  **Вывод:** визуальную сверку с референсом нужно делать на машине с GUI.
- **Модель без зрения**: прикреплённые изображения не анализируются.
  Для сверки с референсом нужен исполнитель с поддержкой изображений.

---

## 5. Воспроизведение

```powershell
cd C:\Users\cyril\Downloads\123\redz_mx_soundboard

# Legacy
python app/voice_studio.py --ui-old

# Новый Tk
python app/voice_studio.py

# Qt/QML
python app/voice_studio.py --ui-qt

# Тесты
python -m unittest discover -s tests -q

# QML-линт
pyside6-qmllint -I app/qtapp/qml app/qtapp/qml/main.qml
```

---

## 6. Приоритеты работ (для продолжения)

1. Добавить PySide6 + qtapp + QML в `.spec` (иначе EXE без Qt)
2. Реализовать страницы `Connect` и `Soundboard` или убрать табы
3. Подключить `promptModel`/`takeModel`/`sampleModel` в `VoicesPage`
4. Перенести оверлей, микшер, хоткеи фраз из Legacy в Qt
5. Визуальная сверка с референсом — только на машине с GUI

---

## 7. Ключевые файлы

```
app/voice_studio.py                  точка входа, 3 режима UI
app/qtapp/main.py                    вход Qt
app/qtapp/app_state.py               состояние
app/qtapp/live_engine.py             движок live
app/qtapp/voice_controller.py        голоса
app/qtapp/models.py                  модели QML
app/qtapp/qml/main.qml               главное окно
app/qtapp/qml/pages/LivePage.qml     главная страница
app/redz_voice_studio_qa.spec        сборка (Qt не добавлен)
dist/RedZVoiceStudio.exe             готовая сборка (без Qt)
```