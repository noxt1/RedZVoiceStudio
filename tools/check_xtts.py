"""Проверка: видит ли движок модель XTTS-v2."""

from __future__ import annotations

import glob
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

hf = os.path.expanduser(r"~\.cache\huggingface\hub")
snaps = glob.glob(os.path.join(hf, "models--tts-hub--XTTS-v2",
                               "snapshots", "*"))
print("snapshot-папок:", len(snaps))

if not snaps:
    print("МОДЕЛЬ НЕ НАЙДЕНА")
    raise SystemExit(1)

snap = snaps[0]
print("путь:", snap)
print()

need = ["config.json", "vocab.json", "model.pth", "dvae.pth",
        "mel_stats.pth", "speakers_xtts.pth"]
ok = True
for fn in need:
    p = os.path.join(snap, fn)
    if os.path.exists(p):
        # разрешаем симлинк
        real = os.path.realpath(p)
        size = os.path.getsize(real)
        flag = "OK " if size > 1000 else "ПУСТО"
        print(f"{flag} {fn:<22} {size / 1024 / 1024:>8.1f} МБ")
        if size <= 1000:
            ok = False
    else:
        print(f"НЕТ {fn}")
        ok = False

print()
if ok:
    print("модель на месте, движок должен её увидеть")
    raise SystemExit(0)
print("модель неполная")
raise SystemExit(1)