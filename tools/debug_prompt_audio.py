"""Диагностика озвучки подсказок — что именно ломается."""
import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import voice_prompts as vp

print("=== 1. Путь к голосу ===")
p = vp._piper_path()
print("piper:", p)
if not p:
    print("КРИТИЧНО: голос не найден")
    sys.exit(1)

print()
print("=== 2. Импорт piper ===")
try:
    from piper import PiperVoice, SynthesisConfig
    print("OK")
except Exception as e:
    print("FAIL:", type(e).__name__, e)
    traceback.print_exc()
    sys.exit(1)

print()
print("=== 3. Загрузка голоса ===")
try:
    voice = PiperVoice.load(p)
    print("OK")
except Exception as e:
    print("FAIL:", type(e).__name__, e)
    traceback.print_exc()
    sys.exit(1)

print()
print("=== 4. Синтез ===")
text = "Привет, меня зовут Кирилл. Сегодня спокойный день."
try:
    out = vp.synthesize_prompt(text, "friendly", out_path="test_prompt.wav")
    print("synthesize_prompt ->", out)
    if out and os.path.exists(out):
        print("размер:", os.path.getsize(out), "байт")
except Exception as e:
    print("FAIL:", type(e).__name__, e)
    traceback.print_exc()

print()
print("=== 5. Воспроизведение ===")
try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    data, sr = sf.read("test_prompt.wav", dtype="float32")
    print(f"аудио: {len(data)/sr:.2f} с, {sr} Гц, пик={float(np.abs(data).max()):.3f}")
    print("устройство вывода по умолчанию:", sd.default.device[1])
    sd.play(data, sr)
    sd.wait()
    print("воспроизведение OK")
except Exception as e:
    print("FAIL:", type(e).__name__, e)
    traceback.print_exc()