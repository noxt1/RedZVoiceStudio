"""Живость речи: пост-обработка синтеза (интонация, паузы, темп).

Проблема: XTTS со сменой temperature/top_p/sound почти не меняет
интонацию (замер: F0 σ 47 -> 33 Гц, разница в пределах шума). Поэтому
«эмоция» определяется верно, но почти не слышна.

Что реально слышно:
  * ИНТОНАЦИЯ — контур высоты: речь падает к концу фразы (декламация),
    а на вопросе поднимается. Плоская фраза звучит как «чтение с листа»,
    живая — как речь.
  * ПАУЗЫ — точки и запятые дают XTTS паузу; без них длинная фраза
    читается одним потоком.
  * ТЕМП и ГРОМКОСТЬ — заметно влияют на восприятие эмоции.

Всё это делается после синтеза, в numpy (движок умеет scipy).

    python tools\\voice_post.py
"""

from __future__ import annotations

import numpy as np

# Насколько меняем высоту тона по тону (доля, 1.0 — без изменений).
TONE_PITCH = {
    "aggressive": -0.05,   # ниже — тяжелее, злее
    "friendly": 0.035,     # чуть выше — теплее
    "energetic": 0.02,
    "neutral": 0.0,
}

# Громкость по тону (множитель).
TONE_GAIN = {
    "aggressive": 1.12,
    "friendly": 0.94,
    "energetic": 1.08,
    "neutral": 1.0,
}

# Насколько глубок контур «декламации» (падение высоты к концу фразы).
TONE_CONTOUR = {
    "aggressive": 0.055,
    "friendly": 0.030,
    "energetic": 0.050,
    "neutral": 0.038,
}

FRAME_SEC = 0.040
OVERLAP = 0.5


def _pitch_contour(audio: np.ndarray, sr: int, depth: float,
                   tail_rise: bool) -> np.ndarray:
    """Прогнать аудио с плавно меняющимся темпом — это и есть интонация.

    Каждый короткий кусочек ресемплится со своим коэффициентом и
    склеивается с перекрытием и сглаживанием. Маленькие изменения
    (±5 %) дают естественный контур высоты без артефактов.
    """
    if audio.size < int(sr * 0.08) or depth <= 0:
        return audio
    frame = max(1, int(sr * FRAME_SEC))
    hop = max(1, int(frame * (1 - OVERLAP)))

    out_len = int(len(audio) * (1.0 + depth * 0.5)) + frame * 2
    out = np.zeros(out_len + frame, dtype=np.float32)
    weight = np.zeros(out_len + frame, dtype=np.float32)
    pos = 0.0
    idx = 0
    total = max(1, len(audio) - 1)
    while idx < len(audio):
        block = audio[idx:idx + frame]
        if block.size < 8:
            break
        # доля фразы, где мы находимся
        frac = idx / total
        # контур: начало выше, конец ниже; на вопросе хвост поднимается
        curve = 1.0 + depth * (0.5 - frac)
        if tail_rise:
            curve += depth * 0.8 * max(0.0, (frac - 0.6) / 0.4)
        # ресемплим блок (меняет и высоту, и длину блока)
        new_len = max(4, int(block.size * curve))
        piece = np.interp(
            np.linspace(0, block.size - 1, new_len),
            np.arange(block.size), block).astype(np.float32)
        # окно строим по длине куска — иначе не сойдётся при склейке
        w = np.hanning(new_len).astype(np.float32)
        piece = piece * w
        start = int(pos)
        end = min(len(out), start + piece.size)
        if end > start:
            out[start:end] += piece[:end - start]
            weight[start:end] += w[:end - start]
        pos += hop
        idx += hop
    # склеиваем перекрытия
    mask = weight > 1e-6
    out[mask] /= weight[mask]
    return out[:int(pos) + frame].astype(np.float32)


def _apply_gain(audio: np.ndarray, gain: float) -> np.ndarray:
    if abs(gain - 1.0) < 0.01 or audio.size == 0:
        return audio
    peak = float(np.abs(audio).max())
    if peak <= 1e-6:
        return audio
    out = audio * gain
    # не даём выйти за 1.0 — иначе будет скрежет
    m = float(np.abs(out).max())
    if m > 0.98:
        out = out * (0.98 / m)
    return out.astype(np.float32)


def shift_pitch(audio: np.ndarray, sr: int, factor: float) -> np.ndarray:
    """Сдвинуть высоту тона на factor (1.0 — без изменений).

    Пересемплирование: 0.95 = голос на полтона ниже, 1.05 — выше.
    Артефактов не даёт (в отличие от блочного контура, который портил
    разборчивость — замер research/bench_contour.py).
    Длительность при этом меняется на 1/factor — для короткой фразы
    это незаметно, а характер голоса меняется сразу.
    """
    if audio is None or audio.size == 0 or abs(factor - 1.0) < 0.005:
        return audio
    new_len = max(8, int(audio.size / factor))
    out = np.interp(np.linspace(0, audio.size - 1, new_len),
                    np.arange(audio.size), audio).astype(np.float32)
    return out


def add_life(audio: np.ndarray, sr: int, tone: str = "neutral",
             text: str = "") -> np.ndarray:
    """Добавить фразе характер по тону: высота голоса и громкость.

    Контур высоты (declination) НЕ используем: замер показал, что блочный
    пересемплил портит и разборчивость, и хорошие фразы (размах 242 ->
    225 Гц). Работает только сдвиг целиком — он артефактов не даёт.
    """
    if audio is None or audio.size == 0:
        return audio
    out = shift_pitch(audio, sr, 1.0 + TONE_PITCH.get(tone, 0.0))
    out = _apply_gain(out, TONE_GAIN.get(tone, 1.0))
    return out.astype(np.float32)


def add_pauses(text: str) -> str:
    """Расставить запятые по паузам — чтобы XTTS не читал одним потоком.

    Перевод (opus-mt) часто приходит без запятых: «Hola que tal me dices
    como estas» — это читается слитно и «тараторится». Ставим запятую
    перед союзами и вводными словами, а в конце — точку.

    Правка C.7.7: добавлены союзы, которые opus-mt склеивает чаще всего
    (y, o, pero, aunque, porque, cuando, si, como, que, para, por, sin),
    и разбивка очень длинных фраз (>14 слов) на предложения — иначе XTTS
    произносит их на одном дыхании, «проглатывая» согласные.
    """
    t = (text or "").strip()
    if not t:
        return t
    import re
    # Союзы, перед которыми пауза действительно уместна. Список раньше
    # включал «y», «o», «ya», «muy», «aqui» — запятая перед ними в испанском
    # не ставится, и XTTS читал фразы рублеными кусками. «que/como/si»
    # тоже убраны: «creo que», «como estas» — не граница паузы.
    joins = (r"\s+(porque|pero|aunque|cuando|mientras|entonces|"
             r"ademas|despues|antes|luego)\b")
    # Пауза имеет смысл только в достаточно длинной фразе.
    if len(t.split()) >= 6:
        t = re.sub(joins, lambda m: ", " + m.group(1), t, flags=re.IGNORECASE)
    # не дублировать запятые
    t = re.sub(r",\s*,+", ",", t)
    t = re.sub(r"\s+,", ",", t)
    # «..., que, ...» — лишняя запятая перед союзом
    t = re.sub(r",\s+(que|como|porque|pero|entonces)\s*,", r", \1", t,
               flags=re.IGNORECASE)
    # Очень длинные фразы режем на предложения, только если в них совсем
    # нет знаков: точка каждые 12 слов внутри живой реплики звучит как
    # чтение по складам. Порог поднят до 20 слов.
    words = t.split()
    if len(words) > 20 and not re.search(r"[.!?]", t):
        parts = []
        for i in range(0, len(words), 14):
            chunk = words[i:i + 14]
            parts.append(" ".join(chunk))
        t = ". ".join(p.strip().rstrip(",") for p in parts if p.strip())
    if not t.endswith((".", "!", "?", "¡", "…")):
        t += "."
    return t


if __name__ == "__main__":
    for s in ("Hola que tal me dices como estas",
              "Eres un maldito cabron no me jodas",
              "¿Qué tal mi juego?"):
        print(f"  {s!r}\n    -> {add_pauses(s)!r}")
