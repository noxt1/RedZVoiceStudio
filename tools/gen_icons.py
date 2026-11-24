"""Генерация SVG-иконок RedZ (24x24, обводка, скруглённые концы).

Иконки рисуются в одном файле-скрипте, чтобы держать единый стиль:
толщина обводки 1.8, скруглённые концы, без заливки, цвет #FFFFFF
(перекрашивается в QML через MultiEffect.colorization).

Запуск:  python tools/gen_icons.py
Результат: app/qtapp/qml/icons/*.svg
"""

from __future__ import annotations

import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "app", "qtapp", "qml", "icons")

W = 24
STROKE = 1.8

# Каждая иконка — набор SVG-примитивов (без обёртки <svg>)
ICONS: dict[str, str] = {
    "home": """
      <path d="M3.5 10.5 12 3.8l8.5 6.7"/>
      <path d="M5.6 12.2V19a1.4 1.4 0 0 0 1.4 1.4h10a1.4 1.4 0 0 0 1.4-1.4v-6.8"/>
      <path d="M9.8 20.4v-5.1h4.4v5.1"/>
    """,
    "mic": """
      <rect x="9.1" y="2.9" width="5.8" height="10.4" rx="2.9"/>
      <path d="M5.6 11.2a6.4 6.4 0 0 0 12.8 0"/>
      <path d="M12 17.7v3.4"/>
      <path d="M8.7 21.1h6.6"/>
    """,
    "settings": """
      <circle cx="12" cy="12" r="3.1"/>
      <path d="M19.5 14.2a1.5 1.5 0 0 0 .3 1.65l.06.06a1.8 1.8 0 1 1-2.55 2.55l-.06-.06a1.5 1.5 0 0 0-1.65-.3 1.5 1.5 0 0 0-.91 1.37v.17a1.8 1.8 0 1 1-3.6 0v-.09a1.5 1.5 0 0 0-.98-1.37 1.5 1.5 0 0 0-1.65.3l-.06.06a1.8 1.8 0 1 1-2.55-2.55l.06-.06a1.5 1.5 0 0 0 .3-1.65 1.5 1.5 0 0 0-1.37-.91h-.17a1.8 1.8 0 1 1 0-3.6h.09a1.5 1.5 0 0 0 1.37-.98 1.5 1.5 0 0 0-.3-1.65l-.06-.06A1.8 1.8 0 1 1 8.49 4.6l.06.06a1.5 1.5 0 0 0 1.65.3h.07a1.5 1.5 0 0 0 .91-1.37v-.17a1.8 1.8 0 0 1 3.6 0v.09a1.5 1.5 0 0 0 .91 1.37 1.5 1.5 0 0 0 1.65-.3l.06-.06a1.8 1.8 0 1 1 2.55 2.55l-.06.06a1.5 1.5 0 0 0-.3 1.65v.07a1.5 1.5 0 0 0 1.37.91h.17a1.8 1.8 0 0 1 0 3.6h-.09a1.5 1.5 0 0 0-1.37.91Z"/>
    """,
    "history": """
      <path d="M3.6 12a8.4 8.4 0 1 0 2.5-6"/>
      <path d="M3.4 3.6v4.6h4.6"/>
      <path d="M12 7.6V12l3.1 1.8"/>
    """,
    "play": "<path d=\"M8 5.4 18.5 12 8 18.6Z\"/>",
    "pause": """
      <rect x="7.4" y="5.2" width="3.4" height="13.6" rx="1.4"/>
      <rect x="13.2" y="5.2" width="3.4" height="13.6" rx="1.4"/>
    """,
    "stop": "<rect x=\"6.4\" y=\"6.4\" width=\"11.2\" height=\"11.2\" rx=\"2.4\"/>",
    "record": "<circle cx=\"12\" cy=\"12\" r=\"5.4\"/>",
    "refresh": """
      <path d="M20.3 11.2a8.4 8.4 0 1 0-.5 4.5"/>
      <path d="M20.6 5.4v5.8h-5.8"/>
    """,
    "trash": """
      <path d="M4.2 6.6h15.6"/>
      <path d="M9.4 6.6V4.9a1.3 1.3 0 0 1 1.3-1.3h2.6a1.3 1.3 0 0 1 1.3 1.3v1.7"/>
      <path d="M6.4 6.6l.9 12.1a1.7 1.7 0 0 0 1.7 1.6h6a1.7 1.7 0 0 0 1.7-1.6l.9-12.1"/>
      <path d="M10.4 10.4v6.2M13.6 10.4v6.2"/>
    """,
    "compare": """
      <path d="M12 3.6v16.8"/>
      <path d="M7.2 8.4 3.6 12l3.6 3.6"/>
      <path d="M16.8 8.4 20.4 12l-3.6 3.6"/>
    """,
    "translate": """
      <path d="M3.6 5.6h8.8"/>
      <path d="M8 3.6v2"/>
      <path d="M10.4 5.6c0 4-3 7.4-6.4 8.8"/>
      <path d="M5.2 9.2c1.1 2.4 3.4 4.2 6.1 4.9"/>
      <path d="m12.8 20.4 4-9.6 4 9.6"/>
      <path d="M14.3 17.2h5"/>
    """,
    "volume": """
      <path d="M4.4 9.4h3.2L12 5.6v12.8l-4.4-3.8H4.4Z"/>
      <path d="M15.6 9.2a4 4 0 0 1 0 5.6"/>
      <path d="M18.1 6.6a7.6 7.6 0 0 1 0 10.8"/>
    """,
    "wave": """
      <path d="M3 12h2.2"/>
      <path d="M7.4 7.6v8.8"/>
      <path d="M11.2 4.8v14.4"/>
      <path d="M15 8.6v6.8"/>
      <path d="M18.8 10.6v2.8"/>
      <path d="M21.6 11.4v1.2"/>
    """,
    "chevron-right": "<path d=\"m9.4 5.6 6.4 6.4-6.4 6.4\"/>",
    "chevron-down": "<path d=\"m5.6 9.4 6.4 6.4 6.4-6.4\"/>",
    "check": "<path d=\"m4.8 12.6 4.8 4.8 9.6-10.8\"/>",
    "close": "<path d=\"M6 6l12 12M18 6 6 18\"/>",
    "folder": """
      <path d="M3.6 6.6a1.4 1.4 0 0 1 1.4-1.4h3.7l2 2.4h7.9a1.4 1.4 0 0 1 1.4 1.4v8.4a1.4 1.4 0 0 1-1.4 1.4H5a1.4 1.4 0 0 1-1.4-1.4Z"/>
    """,
    "star": "<path d=\"m12 3.6 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.8l5.9-.9Z\"/>",
    "bolt": "<path d=\"M13.4 2.6 4.8 13.2h6L10.6 21.4l8.6-10.6h-6Z\"/>",
    "cpu": """
      <rect x="6.6" y="6.6" width="10.8" height="10.8" rx="2"/>
      <rect x="9.8" y="9.8" width="4.4" height="4.4" rx="1"/>
      <path d="M9.4 2.8v3.8M14.6 2.8v3.8M9.4 17.4v3.8M14.6 17.4v3.8M2.8 9.4h3.8M2.8 14.6h3.8M17.4 9.4h3.8M17.4 14.6h3.8"/>
    """,
    "plug": """
      <path d="M8.4 3.4v5.2M15.6 3.4v5.2"/>
      <path d="M5.8 8.6h12.4v3.1a6.2 6.2 0 0 1-12.4 0Z"/>
      <path d="M12 17.9v2.7"/>
    """,
    "keyboard": """
      <rect x="2.6" y="6.4" width="18.8" height="11.2" rx="2"/>
      <path d="M6.4 10h.01M9.8 10h.01M13.2 10h.01M16.6 10h.01M6.4 13.4h.01M9.8 13.4h.01M13.2 13.4h.01M16.6 13.4h.01M8.4 16h7.2"/>
    """,
    "sparkles": """
      <path d="m12 3.4 1.5 4.1 4.1 1.5-4.1 1.5L12 14.6l-1.5-4.1L6.4 9l4.1-1.5Z"/>
      <path d="m18.6 14.4.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8Z"/>
      <path d="m5.4 3.2.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6Z"/>
    """,
    "arrow-right": "<path d=\"M4.4 12h15.2M13.4 5.8 19.6 12l-6.2 6.2\"/>",
    "arrow-down": "<path d=\"M12 4.4v15.2M5.8 13.4 12 19.6l6.2-6.2\"/>",
    "layers": """
      <path d="m12 3.4 8.6 4.6L12 12.6 3.4 8Z"/>
      <path d="m3.4 12.4 8.6 4.6 8.6-4.6"/>
      <path d="m3.4 16.6 8.6 4.6 8.6-4.6"/>
    """,
    "copy": """
      <rect x="8.4" y="8.4" width="11.2" height="11.2" rx="2"/>
      <path d="M15.6 5.6a2 2 0 0 0-2-2H6.4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 2 2"/>
    """,
    "info": """
      <circle cx="12" cy="12" r="8.6"/>
      <path d="M12 11v5.2"/>
      <path d="M12 7.8h.01"/>
    """,
    "warning": """
      <path d="M10.3 3.9 2.6 17.4a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>
      <path d="M12 9.4v4.4M12 17.4h.01"/>
    """,
}

TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
    'viewBox="0 0 {w} {h}" fill="none" stroke="#FFFFFF" '
    'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">'
    "{body}\n</svg>\n"
)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for name, body in ICONS.items():
        svg = TEMPLATE.format(w=W, h=W, sw=STROKE, body=body.strip())
        with open(os.path.join(OUT, f"{name}.svg"), "w", encoding="utf-8") as fh:
            fh.write(svg)
    print(f">>> {len(ICONS)} иконок -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
