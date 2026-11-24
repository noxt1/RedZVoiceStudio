"""Проверка новых возможностей Этапа C.7.2.

1. Две независимые громкости моста.
2. Расширенные языки собеседника + запасной путь перевода.
3. Параметры TTS (связность вместо обрывков).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np


def test_bridge_gains():
    print("=== 1. Две громкости моста ===")
    import mic_bridge
    b = mic_bridge.MicBridge(mic_device=None, render_device=None,
                              monitor_gain=0.8, phrase_gain=1.0)
    print(f"монитор (я слышу): {b.monitor_gain}")
    print(f"кабель (слышат они): {b.phrase_gain}")
    b.set_gains(monitor_gain=0.5, phrase_gain=0.25)
    print(f"после set_gains: monitor={b.monitor_gain}, phrase={b.phrase_gain}")
    assert abs(b.monitor_gain - 0.5) < 1e-6
    assert abs(b.phrase_gain - 0.25) < 1e-6
    # Независимость: меняем одну — вторая не трогается
    b.set_gains(monitor_gain=1.0)
    assert abs(b.phrase_gain - 0.25) < 1e-6, "кабель не должен меняться"
    print("OK: громкости независимы")


def test_langs():
    print()
    print("=== 2. Языки собеседника ===")
    import voice_lang
    print(f"всего языков: {len(voice_lang.PEER_LANGS)}")
    direct = [c for c, _ in voice_lang.PEER_LANGS
              if voice_lang.REVERSE_MT.get(c)]
    fallback = [c for c, _ in voice_lang.PEER_LANGS
                if not voice_lang.REVERSE_MT.get(c) and c not in ("auto", "ru")]
    print(f"прямая модель перевода: {len(direct)} -> {direct}")
    print(f"через английский (Whisper->en->ru): {len(fallback)}")
    assert len(voice_lang.PEER_LANGS) >= 30, "нужно минимум 30 языков"
    assert len(fallback) >= 20, "запасной путь должен покрывать большинство"
    print("OK: языки расширены, запасной путь есть")


def test_tts_params():
    print()
    print("=== 3. Параметры TTS ===")
    import voice_tone
    for name, params in (("NEUTRAL", voice_tone.NEUTRAL),
                         ("AGGRESSIVE", voice_tone.AGGRESSIVE),
                         ("FRIENDLY", voice_tone.FRIENDLY),
                         ("ENERGETIC", voice_tone.ENERGETIC)):
        print(f"{name:11} temp={params['temperature']:.2f} "
              f"top_p={params['top_p']:.2f} top_k={params['top_k']} "
              f"speed={params['speed']:.2f} rep={params['repetition_penalty']:.1f}")
    n = voice_tone.NEUTRAL
    assert n["temperature"] <= 0.80, "temperature слишком высокая — фразы рвутся"
    assert n["repetition_penalty"] >= 8.0, "низкий repetition_penalty -> зацикливание"
    assert n["speed"] <= 1.0, "speed слишком большой — торопится"

    # STREAM_CHUNK
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lt_check", os.path.join(os.path.dirname(__file__), "..", "tools",
                                 "live_translate.py"))
    src = open(spec.origin, encoding="utf-8").read()
    import re
    m = re.search(r'STREAM_CHUNK\s*=\s*int\(os\.environ\.get\("AURALOOM_STREAM_CHUNK",\s*"(\d+)"\)', src)
    chunk = int(m.group(1)) if m else -1
    print(f"STREAM_CHUNK: {chunk}")
    assert chunk >= 25, "чанки слишком мелкие — речь идёт обрывками"
    print("OK: параметры исправлены")


def test_engine_reverse_path():
    print()
    print("=== 4. Запасной путь перевода в движке ===")
    path = os.path.join(os.path.dirname(__file__), "..", "tools",
                        "live_translate.py")
    src = open(path, encoding="utf-8").read()
    assert "_translate_peer_to_ru" in src, "нет запасного пути перевода"
    assert "_transcribe_as_english" in src, "нет перевода на английский"
    assert 'task="translate"' in src, "Whisper не переводит на английский"
    assert "PEER_LANG_CODES" in src, "движок не знает новых языков"
    print("OK: движок поддерживает новые языки и запасной путь")


if __name__ == "__main__":
    test_bridge_gains()
    test_langs()
    test_tts_params()
    test_engine_reverse_path()
    print()
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
