"""Проверка индексов аудиоустройств.

Запомненный индекс микрофона может не совпадать с реальным
(устройства сдвигаются между сессиями/подключениями).

    python tools/diag_devices.py
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import sounddevice as sd
import studio_core as core

print("=== все устройства ===")
for i, d in enumerate(sd.query_devices()):
    ch_in = d.get("max_input_channels", 0)
    ch_out = d.get("max_output_channels", 0)
    kind = []
    if ch_in:
        kind.append(f"in={ch_in}")
    if ch_out:
        kind.append(f"out={ch_out}")
    if not kind:
        continue
    print(f"{i:>3}  {d['name'][:52]:<52}  {' '.join(kind)}  "
          f"默认 {d.get('default_samplerate', 0):.0f} Гц")

print()
mic_idx, mic_name = core.recalled_mic()
print("recalled_mic():", mic_idx, mic_name)

if mic_idx is not None:
    try:
        d = sd.query_devices(mic_idx)
        print(f"индекс {mic_idx} -> {d['name']}")
        print(f"  max_input_channels = {d.get('max_input_channels')}")
    except Exception as exc:
        print(f"индекс {mic_idx} НЕДЕЙСТВИТЕЛЕН: {exc}")

print()
print("=== pick_input_device() ===")
dev, name = core.pick_input_device()
print("вернул:", dev, name)
if dev is not None:
    d = sd.query_devices(dev)
    print(f"  каналов in = {d.get('max_input_channels')}")

print()
print("=== default ===")
try:
    print("sd.default.device =", sd.default.device)
    print("default input =", sd.default.device[0])
except Exception as exc:
    print("ошибка:", exc)