"""Диагностика искажения записи дубля.

Проверяет гипотезу: Recorder пишет на частоте устройства (например 48000),
а файл сохраняется с меткой 44100 -> при проигрывании звучит быстрее/выше.

    python tools/diag_record_rate.py
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

import studio_core as core
import studio_paths as sp
from audiodev import working_rates, best_rate

print("core.SR (метка в WAV):", core.SR)
print()

# что в сохранённых дублях
samples_dir = sp.output_paths()["samples"]
print("=== сохранённые дубли ===")
if not os.path.isdir(samples_dir):
    print("папки нет:", samples_dir)
else:
    try:
        import soundfile as sf
        found = False
        for fn in sorted(os.listdir(samples_dir)):
            if not fn.lower().endswith(".wav"):
                continue
            found = True
            p = os.path.join(samples_dir, fn)
            info = sf.info(p)
            # длительность по файлу и «настоящая» длительность
            # если запись шла на 48к, а метка 44.1к — реальное время короче
            print(f"{fn}: частота={info.samplerate} Гц, "
                  f"каналов={info.channels}, "
                  f"длительность={info.duration:.2f} c, "
                  f"отсчётов={info.frames}")
        if not found:
            print("wav-файлов нет")
    except Exception as exc:
        print("ошибка чтения:", exc)

print()
print("=== реальные частоты микрофона ===")
mic_idx, mic_name = core.recalled_mic()
print("запомненный микрофон:", mic_idx, mic_name)
if mic_idx is not None:
    rates = working_rates(mic_idx, "input")
    print("рабочие частоты:", rates)
    print("best_rate:", best_rate(mic_idx, "input", core.SR))

print()
print("=== вывод ===")
print("Если частота в дубле 44100, а микрофон работает на 48000,")
print("запись звучит на 48000/44100 = 1.088x быстрее (писк).")
print("Правильно: ресемплить в core.SR перед sf.write().")