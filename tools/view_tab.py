"""Проверка вкладок приложения: открыть нужную и снять скриншот.

    python tools\\view_tab.py 2 out.png
"""

from __future__ import annotations

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

TABS = ["Фразы", "Голос", "Микрофон", "Проверка", "В игру", "Живой перевод"]


def main() -> None:
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    out = sys.argv[2] if len(sys.argv) > 2 else "tab.png"

    import voice_studio

    studio = voice_studio.Studio()

    def later() -> None:
        time.sleep(1.0)
        studio.select_tab(index)
        studio.root.update()
        time.sleep(0.6)
        from switch_tab import capture, find_window
        hwnd = find_window()
        if hwnd:
            capture(hwnd, out)
            print(f"вкладка «{TABS[index]}» -> {out}")
        studio.root.after(300, studio.root.destroy)

    threading.Thread(target=later, daemon=True).start()
    studio.run()


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    main()
