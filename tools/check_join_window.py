"""Замер: что даёт окно ожидания паузы собеседника (`PEER_JOIN_END`).

Окно — сколько тишины ждать, прежде чем отдать реплику собеседника на
перевод. Оно склеивает придаточные («..., потому что ...»), но добавляет
столько же задержки КАЖДОЙ фразе. Замер отвечает, где эта граница:

  * «как есть» — настоящие записи подсказок без изменений;
  * «пауза N с» — в самую тихую внутреннюю точку записи вставляется N
    секунд тишины (пауза на запятой). Окно короче паузы рвёт реплику на
    два перевода, окно длиннее — оставляет одну.

Сегментация — НАСТОЯЩИЙ код `LiveEngine._on_loopback_pcm` (VAD, порог от
шума комнаты, склейка), поэтому результат отражает поведение продукта.
Качество перевода на разорванной фразе уже измерено отдельно
(`tools/check_phrase_split.py`: +0,012 chrF у цельной фразы), поэтому
здесь меряется только фрагментация и задержка.

Запуск (Python приложения с PySide6; torch не нужен):

    QT_QPA_PLATFORM=offscreen python tools/check_join_window.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
QTAPP = os.path.join(APP, "qtapp")
SAMPLES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom",
                       "workspace", "voice_samples")
for path in (APP, QTAPP):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as fh:
        sr = fh.getframerate()
        channels = fh.getnchannels()
        raw = fh.readframes(fh.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sr


def quietest_split(audio: np.ndarray, sr: int,
                   window: float = 0.30) -> int | None:
    """Центр самой тихой паузы в середине записи (как в check_phrase_split)."""
    win = int(window * sr)
    step = max(1, int(0.05 * sr))
    lo = int(len(audio) * 0.15)
    hi = int(len(audio) * 0.85) - win
    if hi <= lo:
        return None
    best_pos, best_rms = None, None
    for pos in range(lo, hi, step):
        piece = audio[pos:pos + win].astype(np.float64)
        rms = float(np.sqrt(np.mean(piece ** 2)))
        if best_rms is None or rms < best_rms:
            best_pos, best_rms = pos, rms
    if best_pos is None:
        return None
    return best_pos + win // 2


def trim_edges(audio: np.ndarray, sr: int, rel: float = 0.06) -> np.ndarray:
    """Срезать тишину с краёв (кадры 10 мс, порог от пика записи).

    Нужно для точной паузы: без этого к вставленным gap секундам
    добавляется своя тишина краёв, и окно сравнивается не с gap.
    """
    if audio.size == 0:
        return audio
    win = max(1, int(sr * 0.01))
    n = len(audio) // win
    if n < 3:
        return audio
    frames = audio[:n * win].reshape(n, win).astype(np.float64)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    peak = float(rms.max())
    if peak <= 0:
        return audio
    loud = np.where(rms >= peak * rel)[0]
    if loud.size == 0:
        return audio
    return audio[loud[0] * win:(loud[-1] + 1) * win]


class _Recorder:
    """Заглушка переводчика: запоминает отправленные фразы."""

    def __init__(self) -> None:
        self.ready = True
        self.last_send_error = ""
        self.phrases = 0

    def send_peer_pcm(self, pcm, sr, partial=False, last=True,
                      phrase=None) -> bool:
        if not partial and last:
            self.phrases += 1
        return True


def live_module():
    import live_engine
    return live_engine


def count_phrases(audio: np.ndarray, sr: int, gap: float,
                  join_end: float) -> int:
    """Прогнать звук через настоящую сегментацию и посчитать фразы."""
    live = live_module().LiveEngine()
    live.set_peer_join_end(join_end)
    rec = _Recorder()
    live._translator = rec

    if gap > 0:
        cut = quietest_split(audio, sr)
        if cut is None:
            return 0
        # Края половин обрезаем по энергии: иначе к вставленной паузе
        # добавляется своя тишина записи, и окно сравнивается не с gap.
        head = trim_edges(audio[:cut], sr)
        tail_audio = trim_edges(audio[cut:], sr)
        pad = np.zeros(int(gap * sr), dtype=np.float32)
        audio = np.concatenate([head, pad, tail_audio])

    data = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    block = max(1, int(0.1 * sr))
    for i in range(0, len(data), block):
        live._on_loopback_pcm(data[i:i + block].tobytes(), sr)
    # хвост тишины: гарантированно больше любого окна, чтобы фраза ушла
    tail = np.zeros(int((3.0 + 0.5) * sr), dtype=np.int16)
    for i in range(0, len(tail), block):
        live._on_loopback_pcm(tail[i:i + block].tobytes(), sr)
    return rec.phrases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--windows", default="0.8,1.0,1.3",
                    help="проверяемые окна PEER_JOIN_END, сек")
    ap.add_argument("--gaps", default="0,0.6,0.9,1.15,1.4",
                    help="вставленные паузы на запятой, сек (0 = как есть)")
    args = ap.parse_args()

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])  # noqa: F841
    windows = [float(w) for w in args.windows.split(",") if w.strip()]
    gaps = [float(g) for g in args.gaps.split(",") if g.strip()]

    recs: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(SAMPLES, "p*_take_*.wav"))):
        recs.setdefault(os.path.basename(path)[:3], path)
    keys = sorted(recs)[:args.limit]
    if not keys:
        print(f"нет записей в {SAMPLES}")
        return 1

    rows = []
    for key in keys:
        audio, sr = read_wav(recs[key])
        row = {"id": key, "dur": round(len(audio) / sr, 2)}
        for gap in gaps:
            for window in windows:
                phrases = count_phrases(audio, sr, gap, window)
                row[f"g{gap}/w{window}"] = phrases
        rows.append(row)
        print(f"{key} ({row['dur']} с): " + ", ".join(
            f"пауза {gap:g} с / окно {w:g} с -> {row[f'g{gap}/w{w}']} фраз."
            for gap in gaps for w in windows))

    print("\nсколько записей разорвано на 2+ фразы:")
    summary = {}
    for gap in gaps:
        for window in windows:
            key = f"g{gap}/w{window}"
            split = sum(1 for r in rows if r[key] > 1)
            mean = sum(r[key] for r in rows) / len(rows)
            summary[key] = {"split": split, "mean_phrases": round(mean, 2),
                            "gap": gap, "window": window}
            print(f"  пауза {gap:<4g} с, окно {window:<3g} с: "
                  f"{split} из {len(rows)}  (фраз в среднем {mean:.2f})")

    print("\nзадержка после последнего слова (равна окну):")
    for window in windows:
        print(f"  окно {window:g} с — перевод начинается через ~{window:g} с")

    out = os.path.join(ROOT, "out", "join_window.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"windows": windows, "gaps": gaps,
                   "summary": summary, "rows": rows}, fh,
                  ensure_ascii=False, indent=1)
    print(f"json: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
