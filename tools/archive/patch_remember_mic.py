"""Патч: запоминать микрофон записи и использовать его в мосте.

    python tools\\patch_remember_mic.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "app", "studio_core.py")
GUI = os.path.join(ROOT, "app", "voice_studio.py")


def patch_core() -> None:
    with io.open(CORE, encoding="utf-8") as fh:
        src = fh.read()

    anchor = "def pick_input_device() -> tuple[int | None, str]:"
    helper = '''def _mic_memory_file() -> str:
    """Файл с запомненным микрофоном (тот, с которого шла последняя запись)."""
    return os.path.join(sp.workspace(), "last_mic.json")


def remember_mic(index: int | None, name: str) -> None:
    """Запомнить микрофон: мост и запись будут использовать его."""
    if index is None:
        return
    import json
    try:
        with open(_mic_memory_file(), "w", encoding="utf-8") as fh:
            json.dump({"index": int(index), "name": name}, fh, ensure_ascii=False)
    except Exception:
        pass


def recalled_mic() -> tuple[int | None, str]:
    """Запомненный микрофон (index, name) — если есть."""
    import json
    path = _mic_memory_file()
    if not os.path.exists(path):
        return None, ""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return int(data.get("index", -1)), data.get("name", "")
    except Exception:
        return None, ""


'''
    if "_mic_memory_file" in src:
        print("core: уже пропатчено")
        return
    if anchor not in src:
        print("core: якорь не найден")
        return
    src = src.replace(anchor, helper + anchor, 1)
    with io.open(CORE, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("core: добавлено запоминание микрофона")


def patch_gui() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()

    # 1. при старте — выбирать запомненный микрофон
    old_default = '''        if inputs:
            pool = mic_inputs or inputs
            pick_in = next((i for i, n in pool if i == cur_in), pool[0][0])
'''
    new_default = '''        if inputs:
            pool = mic_inputs or inputs
            rec_i, rec_n = core.recalled_mic()
            pick_in = next((i for i, n in pool if i == cur_in), pool[0][0])
            if rec_i is not None and any(i == rec_i for i, _ in pool):
                pick_in = rec_i  # микрофон, с которого ты записывал
'''
    # 2. при записи — запоминать микрофон
    old_rec = '''        try:
            self.recorder.start(self.recorder.device)
        except Exception as exc:  # noqa: BLE001
            self.voice_status.config(text=f"Микрофон недоступен: {exc}")
            return
'''
    new_rec = '''        try:
            self.recorder.start(self.recorder.device)
            if self.recorder.device is not None:
                import sounddevice as sd
                name = sd.query_devices(self.recorder.device)["name"]
                core.remember_mic(self.recorder.device, name)
        except Exception as exc:  # noqa: BLE001
            self.voice_status.config(text=f"Микрофон недоступен: {exc}")
            return
'''
    # 3. в мосте — сначала запомненный микрофон
    old_bridge = '''        # микрофон для речи: выбранный пользователем (иначе — автоподбор)
        mic_idx = self.in_device
'''
    new_bridge = '''        # микрофон для речи: выбранный пользователем, иначе запомненный,
        # иначе автоподбор
        mic_idx = self.in_device
        if mic_idx is None:
            mic_idx, _ = core.recalled_mic()
'''

    applied = []
    for label, old, new in (("микрофон по умолчанию", old_default, new_default),
                            ("запоминание при записи", old_rec, new_rec),
                            ("микрофон в мосте", old_bridge, new_bridge)):
        if old in src:
            src = src.replace(old, new, 1)
            applied.append(label)
        else:
            print(f"  ! не найдено: {label}")
    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("gui: применено:", ", ".join(applied) if applied else "ничего")


if __name__ == "__main__":
    patch_core()
    patch_gui()
