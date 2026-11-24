"""Тест непрерывного режима: речь режется на фразы по паузам.

Проверяет всю цепочку без микрофона:
  1. VAD-логика (накопление + отсечение по паузе) на реальных записях.
  2. Разбиение потока «речь-пауза-речь» на отдельные фразы.
  3. Что каждая фраза уходит на перевод отдельным запросом.

    python tools\\test_continuous.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import live_tab  # noqa: E402

SR_REC = live_tab.SR_REC
BLOCK_SEC = live_tab.BLOCK_SEC


class FakeStudio:
    """Заглушка приложения: нужна вкладка и root.after."""
    def __init__(self):
        import tkinter as tk
        self.tab_live = tk.Frame()
        self.root = tk.Tk()
        self.root.withdraw()


def split_like_app(samples: list[np.ndarray], silence: float = 0.8,
                   between: float = 0.9) -> list[np.ndarray]:
    """Повторяет логику _cont_callback: режем поток по паузам."""
    silence_blocks = int(silence / BLOCK_SEC)
    between_blocks = int(between / BLOCK_SEC)

    buf: list[np.ndarray] = []
    out: list[np.ndarray] = []
    run = 0
    has_speech = False
    noise = 0.005

    for block in samples:
        rms = float(np.sqrt((block.astype(np.float64) ** 2).mean()))
        if rms < noise * 2.0:
            noise = 0.97 * noise + 0.03 * rms
        thr = max(noise * 3.0, 0.004)
        if rms > thr:
            has_speech = True
            run = 0
        else:
            run += 1
        buf.append(block)
        if run >= silence_blocks and has_speech:
            out.append(np.concatenate(buf))
            buf = []
            has_speech = False
            run = 0
        # пауза между фразами
        if between_blocks and len(buf) >= between_blocks and not has_speech:
            out.append(np.concatenate(buf))
            buf = []
    if buf and has_speech:
        out.append(np.concatenate(buf))
    return out


def main() -> None:
    ws = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                      "workspace")
    samples_dir = os.path.join(ws, "voice_samples")
    files = sorted(f for f in os.listdir(samples_dir) if f.endswith(".wav"))[:4]
    if not files:
        sys.exit("нет записей образца")

    import soundfile as sf
    phrases = []
    for f in files:
        a, sr = sf.read(os.path.join(samples_dir, f), dtype="float32", always_2d=False)
        if a.ndim > 1:
            a = a.mean(axis=1)
        phrases.append(a)

    print("=== 1. одиночная фраза -> одна отправка ===")
    blocks = []
    for a in phrases[:2]:
        n = len(a) // int(SR_REC * BLOCK_SEC)
        for i in range(n):
            blocks.append(a[i * int(SR_REC * BLOCK_SEC):(i + 1) * int(SR_REC * BLOCK_SEC)])
    # хвост тишины -> фраза должна закрыться
    silence = np.zeros(int(SR_REC * 0.8), dtype=np.float32)
    blocks.append(silence)
    parts = split_like_app(blocks)
    print(f"  фраз: {len(parts)} (ожидаем 2)")
    for i, p in enumerate(parts):
        print(f"    [{i}] {len(p) / SR_REC:.2f} с")

    print("\n=== 2. две фразы с паузой -> две отправки ===")
    blocks = []
    for a in phrases[:2]:
        n = len(a) // int(SR_REC * BLOCK_SEC)
        step = int(SR_REC * BLOCK_SEC)
        for i in range(n):
            blocks.append(a[i * step:(i + 1) * step])
        # пауза 0.9 с между фразами
        pause = np.zeros(int(SR_REC * 0.9), dtype=np.float32)
        pstep = int(SR_REC * BLOCK_SEC)
        for i in range(len(pause) // pstep):
            blocks.append(pause[i * pstep:(i + 1) * pstep])
    parts = split_like_app(blocks)
    print(f"  фраз: {len(parts)} (ожидаем 2)")
    for i, p in enumerate(parts):
        print(f"    [{i}] {len(p) / SR_REC:.2f} с")

    print("\n=== 3. обрезка тишины по краям ===")
    a = phrases[0]
    padded = np.concatenate([
        np.zeros(int(SR_REC * 0.5), dtype=np.float32), a,
        np.zeros(int(SR_REC * 0.7), dtype=np.float32)])
    trimmed = live_tab.LiveTab._trim_silence(padded)
    print(f"  было {len(padded) / SR_REC:.2f} с -> стало {len(trimmed) / SR_REC:.2f} с "
          f"(речь {len(a) / SR_REC:.2f} с)")
    ok = abs(len(trimmed) / SR_REC - len(a) / SR_REC) < 0.35
    print(f"  тишина по краям убрана: {'да' if ok else 'нет'}")

    print("\nИТОГ:", "ок — непрерывный режим режет речь на фразы"
          if len(parts) == 2 and ok else "проверь логику")


if __name__ == "__main__":
    main()
