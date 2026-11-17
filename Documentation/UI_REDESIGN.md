# План переделки интерфейса по референсам Auraloom

Источник: `C:\Users\cyril\Downloads\123\референс интерфейса` — брендборд и
9 экранов (нумерация ниже по именам файлов).

Цель: не «перекрасить», а собрать интерфейс заново по композиции референсов —
расположение навигации, герой-баннер, микрофонная орб, панели справа,
нижняя строка состояния, экраны моделей и языков.

---

## 1. Что берём с референсов (по элементам)

| Элемент референса | Куда | Данные в приложении |
|---|---|---|
| Сайдбар: знак + `Auraloom`, пункты Home/Models/Languages/Settings/Diagnostics/About | `main.qml`, `RedZ/LogoMark.qml` | `window.section`, `appState` |
| Карточка движка внизу сайдбара: зелёная точка, «Engine: Ready», имя GPU, VRAM, мини-график | `RedZ/EngineBadge.qml` | `appState.engineState`, `appState.gpuName`, `vramUsed/vramTotal` |
| Герой-баннер: знак, `Auraloom`, подпись, неоновые волны, пилюля «Ready» | `RedZ/HeroBanner.qml` | `brandName`, `brandTagline`, `appState.engineState` |
| Карточка «Live Translation»: заголовок, режим-Auto, шестерёнка | `pages/HomePage.qml` | `appState.mode`, `liveEngine` |
| Микрофонная орб со свечением, «Listening… / Говорите…» | `RedZ/MicOrb.qml` | `liveEngine.level`, `captureOn`, `busy` |
| Волновая дорожка под орб | `RedZ/WaveBars.qml` | `liveEngine.level`, `peerLevel` |
| Панель «Translation Direction»: две страны + стрелка-обмен | `HomePage` | `appState.srcLang/targetLang`, `setTargetLang` |
| Панель «Quality Mode»: Fast / Balanced / Quality / Manual | `RedZ/ModeSegment.qml` | `appState.mode`, `appState.setMode()` |
| Панель «Models Status» / «Active Models»: ASR · MT · TTS + Manage | `HomePage` | `liveEngine.modelsLoaded`, `modelsInfo` |
| «Recent Activity» / «История»: время + перевод + Clear | `HomePage` | `historyModel` |
| «Quick Actions»: плитки Manage Models / Languages / Settings / Diagnostics | `HomePage` | `page.navigate(key)` |
| Нижняя строка: `Auraloom v…`, «Все системы в порядке», наушники | `RedZ/StatusBar.qml` | `brandName`, `appState.engineState`, `appState.bridgeOn` |
| Voice Studio: две орбы (микрофон + динамик), стрелки обмена, волны, режим, статистика | `pages/VoicesPage.qml` | `voiceController`, `liveEngine.lastMetrics` |
| Models & Languages: вкладки ASR/MT/TTS, карточки моделей, статус, quick actions | `pages/ModelsPage.qml` | `liveEngine.catalog`, `models`, `downloads` |

Новые поля, которых в интерфейсе не было (по референсам):

1. **Quality Mode** — переключатель fast/balanced/quality/manual (в ядре уже
   есть `appState.mode`, в UI не было).
2. **Состояние моделей одной строкой** — ASR/MT/TTS с зелёными точками.
3. **Статистика последней реплики** — задержка ASR/MT/TTS, первый звук, RAM,
   VRAM (`liveEngine.lastMetrics`).
4. **Нижняя строка состояния** — версия, «все системы в порядке», наушники.
5. **Герой-баннер** с фирменным знаком и волнами.

## 2. Компоненты (новые)

| Файл | Назначение |
|---|---|
| `RedZ/LogoMark.qml` | знак «A + волна» (готово) |
| `RedZ/NeonWave.qml` | фоновые волны (готово) |
| `RedZ/MicOrb.qml` | орб: кольца, свечение, микрофон, пульсация по уровню |
| `RedZ/WaveBars.qml` | анимированная волновая дорожка |
| `RedZ/EngineBadge.qml` | карточка движка в сайдбаре с VRAM-графиком |
| `RedZ/HeroBanner.qml` | верхний баннер «Auraloom + волны + статус» |
| `RedZ/ModeSegment.qml` | сегмент Fast/Balanced/Quality/Manual |
| `RedZ/StatSpark.qml` | мини-график для статистики |
| `RedZ/StatusBar.qml` | нижняя строка состояния |

## 3. Этапы

### Этап 1 — каркас и главная (в работе)
- Сайдбар: знак, пункты, карточка движка внизу.
- Герой-баннер на главной.
- Нижняя строка состояния вместо футера.
- Главная: Live Translation + орб + волна, Direction, Quality Mode,
  Models Status, Recent Activity, Quick Actions.

Критерий: главная собрана по композиции референса 09/10, все элементы
управляют реальными настройками, `qmllint` 0 ошибок, скриншот.

### Этап 2 — Voice Studio
- Две орбы (микрофон / голос перевода) с волнами и стрелками.
- Панель режима (список с описанием выбранного).
- «Активные модели» тремя плитками.
- «Статистика»: задержка до звука, перевод, RAM, VRAM + спарклайн.
- Сохранить: выбор записей, прослушивание, профили.

### Этап 3 — Models & Languages — СДЕЛАНО (2026-11-18)
- Вкладки ASR / MT / TTS / Языки (пакеты).
- Карточки: название, статус, размер, языки, лицензия, кнопки
  Выбрать / Проверить / Удалить.
- Правая колонка: Model Status, Quick Actions (проверить, докачать, очистить кэш).
- Языки: список пакетов с флагами и статусом.

### Этап 4 — Settings / Diagnostics / About / Phrases
- Настройки по разделам (General / Audio / Translation / Advanced).
- Диагностика: живой журнал, метрики, проверка моделей.
- О проекте: брендборд, версии, лицензии.
- Фразы: карточки с озвучкой в стиле референсов.

### Этап 5 — полировка
- Анимации появления страниц, hover-состояния, фокус с клавиатуры.
- Проверка на 1280×840 и 1920×1080.
- Скриншоты всех экранов, обновление TEST_PLAN.

## 4. Ограничения

- Раскладка не должна ломать привязки к `appState`/`liveEngine`; тесты
  `tests/` проверяют Python-слой, QML — только `qmllint` и запуск.
- Новые сетевые/фоновые процессы не добавляем: только существующие данные.
- Legacy Tk-интерфейс не трогаем (в рабочей папке чужие правки).
