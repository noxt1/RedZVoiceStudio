"""Проверка Legacy UI (6 вкладок) не сломана."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from voice_studio import Studio


def main():
    studio = Studio()
    studio.root.update()
    tabs = [studio.tab_phrases, studio.tab_voice, studio.tab_mic,
            studio.tab_check, studio.tab_game, studio.tab_live]
    print("Legacy вкладок:", len(tabs))
    print("Все созданы:", all(t is not None for t in tabs))
    print("bridge_btn:", hasattr(studio, "bridge_btn"))
    print("_auto_route есть:", hasattr(studio, "_auto_route"))
    print("_start_bridge есть:", hasattr(studio, "_start_bridge"))
    print("live создан:", studio.live is not None)
    studio.root.destroy()
    print("Legacy OK")


if __name__ == "__main__":
    main()
