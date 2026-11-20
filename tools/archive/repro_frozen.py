"""Репро в режиме EXE (frozen): ловит PermissionError с полным трейсбеком.

Имитирует то, что делает собранный EXE: sys.frozen = True, resource_dir()
указывает на корень проекта, app_dir() — на папку с exe.

    python tools\\repro_frozen.py
"""

from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

# притворяемся собранным EXE
sys.frozen = True
sys._MEIPASS = ROOT
sys.executable = os.path.join(ROOT, "dist", "RedZVoiceStudio.exe")

import studio_paths as sp  # noqa: E402
import studio_core as core  # noqa: E402


def main() -> None:
    ws = sp.workspace()
    print("workspace:", ws)
    print("resource_dir:", sp.resource_dir())
    print("app_dir:", sp.app_dir())

    # 1) копирование инструментов (то, что делает EXE при первом запуске)
    try:
        td = sp.workspace_tools()
        print("workspace_tools OK:", td)
    except Exception:
        print("\n=== ОШИБКА workspace_tools ===")
        traceback.print_exc()

    # 2) payload
    payload = [{"id": "01", "text": "Que chido, guay!", "ru": ""}]
    try:
        p = os.path.join(ws, "phrases_payload.json")
        with open(p, "w", encoding="utf-8") as fh:
            import json
            json.dump(payload, fh, ensure_ascii=False)
        print("payload OK")
    except Exception:
        print("\n=== ОШИБКА payload ===")
        traceback.print_exc()

    # 3) запуск движка ровно как в clone_all
    try:
        script = os.path.join(sp.workspace_tools(), "xtts_clone.py")
        out = os.path.dirname(sp.output_paths()["out_wav"])
        code = core.run_engine([script, "--reference",
                                os.path.join(ws, "reference.wav"),
                                "--attempts", "1", "--expressiveness", "2",
                                "--out", out, "--texts-file",
                                os.path.join(ws, "phrases_payload.json")],
                               on_line=lambda line: print("  движок:", line))
        print("run_engine код:", code)
    except Exception:
        print("\n=== ОШИБКА run_engine ===")
        traceback.print_exc()


if __name__ == "__main__":
    main()
