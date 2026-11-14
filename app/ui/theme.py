"""Тема Liquid Glass для RedZ Voice Studio.

Цвета, шрифты, отступы, радиусы скругления — единый источник verdad,
совпадающий с ui_visual_tokens.json (утверждённый второй концепт дизайна).
Никаких констант, размазанных по коду.
"""

from __future__ import annotations

import ctypes
import os
import sys

# ---------------------------------------------------------------------------
# Палитра (из ui_visual_tokens.json)
# ---------------------------------------------------------------------------

WINDOW_BG = "#0B1118"        # тёмный фон окна
BG = WINDOW_BG               # алиас для совместимости
MICA_FALLBACK = "#0E141C"    # фон под Mica (если не поддерживается — сплошной)
SIDEBAR_BG = "#101923"       # боковая панель
SURFACE_1 = "#151F2A"        # основная карточка
SURFACE_2 = "#1B2936"        # альтернативная карточка / внутренняя панель
SURFACE_3 = "#223342"        # элементы управления
SURFACE_HOVER = "#263A4B"    # наведение
SURFACE_PRESSED = "#30495C"  # нажатое состояние
ACTIVE = SURFACE_PRESSED     # алиас для совместимости
BORDER_SUBTLE = "#2A3B4A"    # мягкая граница
BORDER_FOCUS = "#6CBDEB"     # граница при фокусе
TEXT_PRIMARY = "#EDF5FB"     # основной текст
FG = TEXT_PRIMARY            # алиас для совместимости
TEXT_SECONDARY = "#A8BAC8"   # второстепенный текст
TEXT_MUTED = "#718696"       # приглушённый текст
DIM = TEXT_MUTED             # алиас для совместимости
ACCENT = "#8BCFFF"           # акцент (голубой)
ACCENT_STRONG = "#55B7F0"    # насыщенный акцент
ACCENT_GLOW = "#315B78"      # подсветка акцента
INCOMING_ACCENT = "#9CBFFF"  # акцент входящего перевода
OUTGOING_ACCENT = "#83D4FF"  # акцент исходящего перевода
SUCCESS = "#55D6A2"          # зелёный (OK / готово)
WARNING = "#E9BD72"          # жёлтый (предупреждение)
WARN = WARNING               # алиас для совместимости
ERROR = "#F07878"            # красный (ошибка)
BAD = ERROR                  # алиас для совместимости
GOOD = "#55D6A2"             # зелёный (OK / готово)
HOVER = SURFACE_HOVER        # цвет при наведении
TRACK = "#30414F"            # трек слайдера
SLIDER_FILL = "#79C7F4"      # заполнение слайдера

# ---------------------------------------------------------------------------
# Шрифты (из ui_visual_tokens.json)
# ---------------------------------------------------------------------------

FONT_FAMILY = "Segoe UI Variable"   # предпочитаемый шрифт
FONT_FALLBACK = "Segoe UI"          # fallback

FONT_APP_TITLE = ("Segoe UI Variable", 15, "bold")       # заголовок приложения
FONT_PAGE_TITLE = ("Segoe UI Variable", 21, "bold")      # заголовок страницы
FONT_CARD_TITLE = ("Segoe UI Variable", 13, "bold")      # заголовок карточки
FONT_H2 = FONT_CARD_TITLE                                # алиас для совместимости
FONT_BODY = ("Segoe UI Variable", 10, "normal")          # основной текст
FONT_SECONDARY = ("Segoe UI Variable", 9, "normal")      # подписи, метки
FONT_METRIC = ("Segoe UI Variable", 23, "normal")        # большие метрики (задержка, RMS)
FONT_MONO = ("Consolas", 10, "normal")                   # код, хоткеи, логи

# ---------------------------------------------------------------------------
# Отступы (из ui_visual_tokens.json)
# ---------------------------------------------------------------------------

SPACE_XXS = 4
SPACE_XS = 8
SPACE_SM = 12
SPACE_MD = 16
SPACE_LG = 22
SPACE_XL = 28
SPACE_XXL = 36

# Обратная совместимость со старыми именами отступов
SPACE_S = SPACE_XS   # 8
SPACE_M = SPACE_SM   # 12
SPACE_L = SPACE_MD   # 16
SPACE_XL_OLD = SPACE_LG  # 22 (был SPACE_XL, теперь 28)

# ---------------------------------------------------------------------------
# Радиусы скругления (из ui_visual_tokens.json)
# ---------------------------------------------------------------------------

RADIUS_WINDOW = 20   # визуальный радиус окна
RADIUS_CARD = 18     # карточки по умолчанию
RADIUS_INNER = 12    # внутренняя панель
RADIUS_CONTROL = 10  # элементы управления
RADIUS_PILL = 999    # капсула (круглые кнопки)
BORDER_WIDTH = 1     # толщина границы

# ---------------------------------------------------------------------------
# Время анимации (мс)
# ---------------------------------------------------------------------------

HOVER_MS = 120
FOCUS_MS = 140
SIDEBAR_MS = 150

# ---------------------------------------------------------------------------
# Mica / фон окна (Windows 11 22H2+)
# ---------------------------------------------------------------------------

MICA_ENABLED = False  # проверяется при инициализации окна

_DWMWA_SYSTEMBACKDROP_TYPE = 38
_MICA = 2  # DWM_SYSTEMBACKDROP_TYPE_MICA


def try_mica(hwnd: int) -> bool:
    """Попытаться включить Mica-фон окна через DWM.

    Возвращает True, если атрибут успешно установлен. На Windows 10 или
    если DWM не поддерживает Mica — False, окно останется со сплошным фоном.
    """
    global MICA_ENABLED
    if sys.platform != "win32":
        MICA_ENABLED = False
        return False
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            _DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(ctypes.c_int(_MICA)),
            ctypes.sizeof(ctypes.c_int),
        )
        MICA_ENABLED = True
        return True
    except Exception:
        MICA_ENABLED = False
        return False


def apply_window_theme(root) -> bool:
    """Применить тёмную тему к корневому окну Tkinter.

    Пытается включить Mica. Если не получается — fallback на сплошной
    тёмный цвет. Возвращает True, если Mica включён.
    """
    root.update_idletasks()
    hwnd = root.winfo_id()
    ok = try_mica(hwnd)
    root.configure(bg=WINDOW_BG if not ok else MICA_FALLBACK)
    return ok
