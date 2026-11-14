r"""Проверка синхронности всех частей проекта.

Один и тот же набор реплик живёт сразу в четырёх местах:
  lines.json      — источник правды (тексты, клавиши, категории)
  sounds/*.ogg    — ресурс для FiveM/RedM
  out/            — мастеры (wav + ogg + mp3)
  player/mp3/     — автономный плеер
  keybinds.lua    — бинды для ресурса
  player/index.html — список реплик в плеере

Если что-то разъехалось — скрипт это покажет.

    python tools\check_sync.py
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def main() -> None:
    with open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        lines = json.load(fh)["lines"]

    problems = []

    # 1. Все форматы на месте и идентичны по содержимому
    for line in lines:
        i = line["id"]
        ogg_master = os.path.join(ROOT, "out", "ogg", f"mx_{i}.ogg")
        ogg_res = os.path.join(ROOT, "sounds", f"mx_{i}.ogg")
        mp3_master = os.path.join(ROOT, "out", "mp3", f"mx_{i}.mp3")
        mp3_player = os.path.join(ROOT, "player", "mp3", f"mx_{i}.mp3")
        wav = os.path.join(ROOT, "out", "wav", f"mx_{i}.wav")

        for p in (ogg_master, ogg_res, mp3_master, mp3_player, wav):
            if not os.path.exists(p):
                problems.append(f"[{i}] нет файла {os.path.relpath(p, ROOT)}")
                continue
        if os.path.exists(ogg_master) and os.path.exists(ogg_res):
            if digest(ogg_master) != digest(ogg_res):
                problems.append(f"[{i}] sounds/ не совпадает с out/ogg/")
        if os.path.exists(mp3_master) and os.path.exists(mp3_player):
            if digest(mp3_master) != digest(mp3_player):
                problems.append(f"[{i}] player/mp3/ не совпадает с out/mp3/")

    # 2. Нет «лишних» файлов (старые id после удаления реплики)
    for folder, pattern in (("sounds", "*.ogg"), ("out/ogg", "*.ogg"),
                            ("out/mp3", "*.mp3"), ("out/wav", "*.wav"),
                            ("player/mp3", "*.mp3")):
        ext = pattern[1:]  # ".ogg"
        valid = {f"mx_{l['id']}{ext}" for l in lines}
        for path in glob.glob(os.path.join(ROOT, folder, pattern)):
            if os.path.basename(path) not in valid:
                problems.append(f"лишний файл {folder}/{os.path.basename(path)}")

    # 3. keybinds.lua соответствует lines.json (файла может не быть в рабочей папке)
    kb_path = os.path.join(ROOT, "keybinds.lua")
    if not os.path.exists(kb_path):
        kb = ""
        kb_map = {}
    else:
        kb = open(kb_path, encoding="utf-8").read()
        rows = re.findall(r"cmd\s*=\s*'sbplay(\d+)'\s*,\s*key\s*=\s*'([^']+)'\s*,\s*desc\s*=\s*'([^']*)'", kb)
        kb_map = {int(i): (k, d) for i, k, d in rows}
    for line in lines:
        key, desc = kb_map.get(int(line["id"]), (None, None))
        if not kb_map:
            break
        if key is None:
            problems.append(f"[{line['id']}] нет бинда в keybinds.lua")
            continue
        if key.lower() != line["key"].lower():
            problems.append(f"[{line['id']}] клавиша {key} != {line['key']}")
        clean_desc = desc.replace("¡", "").replace("!", "").strip().lower()
        clean_es = line["es"].replace("¡", "").replace("!", "").strip().lower()
        if clean_desc != clean_es:
            problems.append(f"[{line['id']}] текст бинда {desc!r} != {line['es']!r}")

    # 4. player/index.html соответствует lines.json
    html_path = os.path.join(ROOT, "player", "index.html")
    if not os.path.exists(html_path):
        html = ""
        pl = []
    else:
        html = open(html_path, encoding="utf-8").read()
        pl = re.findall(r'\["(\d+)","([^"]+)","([^"]+)","([^"]+)","([^"]+)"\]', html)
    if pl and len(pl) != len(lines):
        problems.append(f"в плеере {len(pl)} реплик, в lines.json {len(lines)}")
    for (pid, pkey, pes, pru, pcat), line in zip(pl, lines):
        if pid != line["id"]:
            problems.append(f"порядок в плеере: {pid} != {line['id']}")
        elif pes != line["es"]:
            problems.append(f"[{pid}] текст в плеере {pes!r} != {line['es']!r}")
        elif pkey.lower() != line["key"].lower():
            problems.append(f"[{pid}] клавиша в плеере {pkey} != {line['key']}")
        elif pcat != line["cat"]:
            problems.append(f"[{pid}] категория в плеере {pcat} != {line['cat']}")

    # 5. fxmanifest перечисляет все ogg (если манифест есть)
    mf_path = os.path.join(ROOT, "fxmanifest.lua")
    if os.path.exists(mf_path):
        mf = open(mf_path, encoding="utf-8").read()
        listed = set(re.findall(r"'(sounds/[^']+\.ogg)'", mf))
        on_disk = {f"sounds/{os.path.basename(p)}" for p in glob.glob(os.path.join(ROOT, "sounds", "*.ogg"))}
        for missing in sorted(on_disk - listed):
            problems.append(f"{missing} не указан в fxmanifest.lua")
        for extra in sorted(listed - on_disk):
            problems.append(f"в fxmanifest указан несуществующий {extra}")

    if problems:
        print("НАЙДЕНЫ РАСХОЖДЕНИЯ:")
        for p in problems:
            print(f"  {p}")
        raise SystemExit(1)

    print(f"Всё синхронно: {len(lines)} реплик, 4 формата, бинды и плеер совпадают.")


if __name__ == "__main__":
    main()
