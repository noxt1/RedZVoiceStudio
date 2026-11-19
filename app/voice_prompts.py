"""Озвучка подсказок для записи голоса — с интонацией и подачей.

Зачем: при клонировании важно, чтобы референс содержал РАЗНЫЕ эмоции
(возмущение, радость, спокойствие). Если человек читает всё ровно,
XTTS клонирует «робота». Поэтому перед записью фразы приложение
проигрывает образец: как эта фраза должна звучать.

Использует Piper (голоса уже в проекте): для каждой эмоции — своя
скорость и вариант голоса. Это НЕ клон, а эталон подачи.

Эмоции (из PROMPTS_RU размечены по смыслу):
  * angry     — возмущение, резко, быстрее
  * friendly  — тепло, мягче, медленнее
  * neutral   — спокойно, обычный темп
  * energetic — энергично, чуть быстрее и громче
"""

from __future__ import annotations

import os
import re
import sys

# Голоса Piper в проекте (voices/): es_MX-ald-medium, es_MX-claude-high
VOICE_ES = "es_MX-ald-medium"
VOICE_ES_ALT = "es_MX-claude-high"

# Параметры подачи по эмоциям: (скорость, полутон, громкость)
_TONE_STYLE = {
    "angry":     {"length_scale": 0.92, "volume": 1.0},
    "friendly":  {"length_scale": 1.10, "volume": 0.9},
    "neutral":   {"length_scale": 1.00, "volume": 0.95},
    "energetic": {"length_scale": 0.95, "volume": 1.0},
}

# Слова-маркеры эмоций в русских подсказках
_ANGRY_WORDS = (
    "не фигня", "чёрт", "черт", "damn", "fuck", "бля", "ублюд", "сран",
    "не смейся", "замолчи", "отдай", "не двигайся", "руки вверх",
    "стреля", "сдаюсь", "убью", "нож", "оружие", "брось",
)
_FRIENDLY_WORDS = (
    "привет", "как дела", "спасибо", "друг", "люблю", "хорошо", "круто",
    "давай", "пойдём", "пойдем", "рад", "пожалуйста",
)
_ENERGETIC_WORDS = (
    "быстрее", "давай", "вперёд", "вперед", "погнали", "хватит", "хватит",
    "подъём", "подъем", "слушайте", "начинаем",
)


def detect_emotion(text: str) -> str:
    """Определить эмоцию фразы по ключевым словам.

    Возвращает: angry / friendly / energetic / neutral.
    """
    t = (text or "").lower()
    if not t:
        return "neutral"
    angry = sum(1 for w in _ANGRY_WORDS if w in t)
    friendly = sum(1 for w in _FRIENDLY_WORDS if w in t)
    energetic = sum(1 for w in _ENERGETIC_WORDS if w in t)
    best = max(angry, friendly, energetic)
    if best == 0:
        return "neutral"
    if best == angry:
        return "angry"
    if best == friendly:
        return "friendly"
    return "energetic"


def _piper_path() -> str | None:
    """Путь к .onnx голоса Piper (es_MX-ald-medium).

    Ищем в: бандле EXE (_MEIPASS/voices), папке проекта (исходники),
    рабочей папке. Возвращаем первый существующий > 1 МБ.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # исходники: app/../voices
        os.path.join(here, "..", "voices"),
        os.path.join(here, "..", "..", "voices"),
    ]
    # бандл PyInstaller: sys._MEIPASS/voices
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, os.path.join(meipass, "voices"))
    # рабочая папка
    try:
        import studio_paths as sp
        candidates.append(os.path.join(sp.workspace(), "voices"))
    except Exception:
        pass

    for base in candidates:
        try:
            p = os.path.join(os.path.abspath(base), f"{VOICE_ES}.onnx")
            if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
                return p
        except Exception:
            continue
    return None


def _norm(text: str) -> str:
    """Нормализация текста для сопоставления с готовым референсом."""
    t = " ".join((text or "").lower().split())
    for ch in ("¿", "¡", ",", ".", "!", "?"):
        t = t.replace(ch, "")
    return t.strip()


def bundled_for(text: str) -> str | None:
    """Путь к ГОТОВОМУ wav-образцу для этого текста (None, если нет).

    Готовые образцы лежат в voices/prompts — они уже записаны и едут
    вместе с программой, поэтому синтез не нужен.
    """
    try:
        import prompt_library as plib
    except Exception:
        return None
    try:
        items = plib.manifest()
    except Exception:
        return None
    key = _norm(text)
    if not key:
        return None
    for it in items:
        if _norm(it.get("es", "")) == key or _norm(it.get("ru", "")) == key:
            return plib.audio_path(it.get("index", 0))
    return None


def synthesize_prompt(text: str, emotion: str = "",
                      out_path: str | None = None) -> str | None:
    """Озвучить фразу-подсказку с нужной интонацией.

    Возвращает путь к wav-файлу или None, если озвучка недоступна.
    Сначала используется готовый референс из voices/prompts; если его
    нет — синтез Piper (движок или локальный piper).
    """
    if not text or not text.strip():
        return None
    # 1. Готовый образец из поставки — мгновенно и без нагрузки
    ready = bundled_for(text)
    if ready:
        return ready
    emo = emotion or detect_emotion(text)
    style = _TONE_STYLE.get(emo, _TONE_STYLE["neutral"])
    onnx = _piper_path()
    if not onnx:
        return None
    try:
        from piper import PiperVoice, SynthesisConfig
    except Exception:
        return None
    try:
        voice = PiperVoice.load(onnx)
        cfg = SynthesisConfig(
            length_scale=style["length_scale"],
            volume=style["volume"],
        )
        chunks = list(voice.synthesize(text, cfg))
        if not chunks:
            return None
        import numpy as np
        import soundfile as sf
        audio = np.concatenate(
            [np.asarray(c.audio_float_array, dtype=np.float32)
             for c in chunks])
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 0.95:
            audio = audio * (0.95 / peak)
        if out_path is None:
            import tempfile
            fd, out_path = tempfile.mkstemp(suffix=".wav", prefix="prompt_")
            os.close(fd)
        sf.write(out_path, audio, 22050, subtype="PCM_16")
        return out_path
    except Exception:
        return None


def emotion_label(emotion: str) -> str:
    """Человекочитаемая подсказка: как произносить."""
    return {
        "angry": "возмущённо, резко",
        "friendly": "тепло, дружелюбно",
        "energetic": "энергично, живо",
        "neutral": "спокойно, обычно",
    }.get(emotion, "спокойно")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    samples = [
        "Привет, меня зовут Кирилл. Сегодня спокойный день.",
        "Не фигня, брат, давай работать!",
        "Не двигайся, руки вверх, оружие брось!",
        "Как круто, всё отлично! У меня тут всё хорошо.",
    ]
    for s in samples:
        emo = detect_emotion(s)
        print(f"{emo:10} | {s}")