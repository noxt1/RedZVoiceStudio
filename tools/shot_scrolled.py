"""Скриншот вкладки с прокруткой (для проверки интерфейса).

    python tools\\shot_scrolled.py <индекс вкладки> <файл.png> [позиция 0..1]
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import voice_studio  # noqa: E402
from shot import capture  # noqa: E402


def main() -> None:
    tab = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    out = sys.argv[2] if len(sys.argv) > 2 else "tab.png"
    frac = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

    studio = voice_studio.Studio()
    studio.root.after(400, lambda: studio.select_tab(tab))

    def scroll() -> None:
        try:
            studio.live.scroller.canvas.yview_moveto(frac)
        except Exception:
            pass

    studio.root.after(1400, scroll)

    def snap() -> None:
        try:
            hwnd = int(studio.root.winfo_id())
            capture(hwnd, out)
            print("saved", out)
        except Exception as exc:  # noqa: BLE001
            print("ошибка снимка:", exc)
        studio.root.quit()

    studio.root.after(2200, snap)
    studio.root.mainloop()


if __name__ == "__main__":
    main()
