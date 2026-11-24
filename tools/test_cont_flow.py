"""Тест непрерывного режима в GUI: эмулируем поток микрофона.

Микрофон не нужен: подсовываем колбэку записи заранее подготовленные
фрагменты с паузами и смотрим, что приложение само делит речь на фразы
и отправляет их на перевод.

    python tools\\test_cont_flow.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import voice_studio  # noqa: E402
import live_tab as lt  # noqa: E402


def main() -> None:
    import soundfile as sf

    ws = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                      "workspace")
    samples_dir = os.path.join(ws, "voice_samples")
    files = sorted(f for f in os.listdir(samples_dir) if f.endswith(".wav"))[:2]
    if not files:
        sys.exit("нет записей образца")

    studio = voice_studio.Studio()
    live = studio.live
    step = int(lt.SR_REC * lt.BLOCK_SEC)

    # готовим «поток»: фраза -> пауза -> фраза -> пауза
    # Пауза делаем 1.2 с: короче VAD не отличает паузу от пауз внутри речи.
    stream = []
    for f in files:
        a, sr = sf.read(os.path.join(samples_dir, f), dtype="float32", always_2d=False)
        if a.ndim > 1:
            a = a.mean(axis=1)
        n = len(a) // step
        for i in range(n):
            stream.append(a[i * step:(i + 1) * step])
        pause = np.zeros(int(lt.SR_REC * 1.2), dtype=np.float32)
        for i in range(len(pause) // step):
            stream.append(pause[i * step:(i + 1) * step])

    # подменяем отправку на перевод: считаем запросы
    sent = []
    orig_queue = live._queue_translate

    def spy(pcm, sr=lt.SR_REC):
        sent.append((len(pcm) / sr, pcm.copy()))
        orig_queue(pcm, sr)

    # важно: подменяем на ЭКЗЕМПЛЯРЕ (метод ищется через self)
    live._queue_translate = spy
    live._cont_on = True

    # эмулируем колбэк микрофона
    sent_now = {"n": 0}

    def fake_callback(indata, frames, time_info, status):
        if sent_now["n"] >= len(stream):
            return
        block = stream[sent_now["n"]]
        sent_now["n"] += 1
        live._cont_callback(block.reshape(-1, 1), frames, time_info, status)

    live._cont_on = True

    print(f"блоков в «потоке»: {len(stream)}")
    # прогоняем поток через НАСТОЯЩИЙ колбэк (не через подменённый)
    real_cb = lt.LiveTab._cont_callback.__get__(live, lt.LiveTab)
    for block in stream:
        real_cb(block.reshape(-1, 1), 0, None, None)
    print(f"фраз отправлено на перевод: {len(sent)} (ожидаем 2)")
    for i, (dur, _pcm) in enumerate(sent):
        print(f"  [{i}] {dur:.2f} с")

    # теперь реально отправляем в движок (очередь уже заполнена)
    live._cont_on = False
    try:
        if live.translator:
            live.translator.stop()
    except Exception:
        pass
    try:
        studio.root.destroy()
    except Exception:
        pass

    ok = len(sent) == 2
    print("\nИТОГ:", "ок — речь режется на фразы" if ok else "НЕ ОК")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
