"""Проверка мягкого лимитера и громкостей (Этап C.7.3)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np


def test_soft_limit():
    print("=== Мягкий лимитер (вместо жёсткого clip) ===")
    from mic_bridge import _soft_limit

    # Тихий сигнал не трогаем
    x = np.array([0.1, -0.2, 0.3], dtype=np.float32)
    y = _soft_limit(x)
    assert np.array_equal(x, y), "тихий сигнал изменился"
    print("тихий сигнал: без изменений OK")

    # Пик сжимается, но не срезается
    x = np.array([1.5, -1.5, 0.2], dtype=np.float32)
    y = _soft_limit(x)
    peak = float(np.abs(y).max())
    print(f"пик 1.5 -> {peak:.3f}")
    assert peak <= 1.0, "пик не сжат"
    assert peak > 0.95, "пик срезан жёстко — будет «проглоченный» звук"

    # Реальный микс: микрофон + перевод
    rs = np.random.RandomState(0)
    mic = (rs.randn(512) * 0.5).astype(np.float32)
    phrase = (rs.randn(512) * 0.5).astype(np.float32)
    mix = mic + phrase
    out = _soft_limit(mix)
    print(f"микс: пик {float(np.abs(mix).max()):.3f} -> "
          f"{float(np.abs(out).max()):.3f}")
    assert float(np.abs(out).max()) <= 1.0
    # Форма сохранилась (не срезана): корреляция высокая
    corr = float(np.corrcoef(mix, out)[0, 1])
    print(f"корреляция микса до/после: {corr:.4f}")
    assert corr > 0.95, "форма сигнала искажена — будет «проглоченный» звук"
    print("OK: пики мягко сжимаются, форма сохраняется")


def test_gains():
    print()
    print("=== Три громкости ===")
    import mic_bridge
    b = mic_bridge.MicBridge(mic_device=None, render_device=None,
                              monitor_gain=0.8, phrase_gain=1.0)
    b.out_gain = 1.0
    b.set_gains(monitor_gain=0.5, phrase_gain=0.3, out_gain=0.4)
    print(f"монитор={b.monitor_gain} phrase={b.phrase_gain} out={b.out_gain}")
    assert abs(b.monitor_gain - 0.5) < 1e-6
    assert abs(b.phrase_gain - 0.3) < 1e-6
    assert abs(b.out_gain - 0.4) < 1e-6
    print("OK: три независимые громкости")


def test_tts_params():
    print()
    print("=== Параметры TTS (без зацикливания) ===")
    import voice_tone
    n = voice_tone.NEUTRAL
    print(f"NEUTRAL: temp={n['temperature']} top_p={n['top_p']} "
          f"top_k={n['top_k']} speed={n['speed']} rep={n['repetition_penalty']}")
    # repetition_penalty должен быть высоким (дефолт XTTS = 10) — иначе зацикливание
    assert n["repetition_penalty"] >= 8.0, "низкий repetition_penalty -> зацикливание"
    assert 0.70 <= n["temperature"] <= 0.80, "temperature вне рабочего диапазона XTTS"
    assert n["top_k"] == 50 and n["top_p"] == 0.85, "top_k/top_p должны быть дефолтными"
    assert n["speed"] <= 1.0, "speed > 1 -> торопливость"

    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py"), encoding="utf-8").read()
    m = re.search(r'STREAM_CHUNK\s*=\s*int\(os\.environ\.get\("REDZ_STREAM_CHUNK",\s*"(\d+)"\)', src)
    chunk = int(m.group(1))
    print(f"STREAM_CHUNK: {chunk}")
    assert chunk >= 25
    assert "overlap_wav_len=2048" in src, "нет увеличенного перекрытия чанков"
    print("OK: параметры исправлены")


if __name__ == "__main__":
    test_soft_limit()
    test_gains()
    test_tts_params()
    print()
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
