"""Библиотека готовых звуковых подсказок (референсов интонации).

Файлы лежат в voices/prompts/*.wav и озвучены заранее голосом Piper
es_MX-claude-high (Apache-2.0). Они едут вместе с программой — поэтому
образец интонации проигрывается мгновенно, без сети и без синтеза.

Источник: tools/build_prompt_audio.py
Лицензии: voices/THIRD-PARTY-NOTICES.md
"""

from __future__ import annotations

import json
import os
import sys

_MANIFEST_CACHE: list[dict] | None = None


def _candidate_dirs() -> list[str]:
    """Где искать папку voices/prompts."""
    out: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(os.path.join(meipass, "voices", "prompts"))
    here = os.path.dirname(os.path.abspath(__file__))
    out.append(os.path.join(here, "..", "voices", "prompts"))
    out.append(os.path.join(here, "..", "..", "voices", "prompts"))
    try:
        import studio_paths as sp
        out.append(os.path.join(sp.workspace(), "voices", "prompts"))
    except Exception:
        pass
    return [os.path.abspath(p) for p in out]


def prompt_dir() -> str | None:
    """Папка с готовыми WAV (None, если их нет)."""
    for base in _candidate_dirs():
        if os.path.isdir(base) and os.path.exists(os.path.join(base, "manifest.json")):
            return base
    for base in _candidate_dirs():
        if os.path.isdir(base):
            return base
    return None


def available() -> bool:
    """Есть ли готовые референсы в поставке."""
    d = prompt_dir()
    return bool(d) and os.path.exists(os.path.join(d, "manifest.json"))


def manifest() -> list[dict]:
    """Список подсказок: index, ru, es, emotion, emotion_label, file, duration."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE

    items: list[dict] = []
    d = prompt_dir()
    if d:
        mpath = os.path.join(d, "manifest.json")
        if os.path.exists(mpath):
            try:
                with open(mpath, encoding="utf-8") as fh:
                    data = json.load(fh)
                items = list(data.get("items") or [])
            except Exception:
                items = []

    if not items:
        # Запасной вариант: собрать список из кода, без аудио.
        try:
            import studio_core as core
            from voice_prompts import emotion_label
            for i, (ru, es) in enumerate(zip(core.PROMPTS_RU, core.PROMPTS_ES)):
                emo = (core.PROMPT_EMOTIONS[i]
                       if i < len(core.PROMPT_EMOTIONS) else "neutral")
                items.append({
                    "index": i,
                    "file": f"prompt_{i + 1:02d}.wav",
                    "ru": ru,
                    "es": es.replace("{name}", core.PROMPT_REF_NAME),
                    "emotion": emo,
                    "emotion_label": emotion_label(emo),
                    "duration": 0.0,
                })
        except Exception:
            items = []

    _MANIFEST_CACHE = items
    return items


def audio_path(index: int) -> str | None:
    """Путь к готовому WAV подсказки (None, если файла нет)."""
    d = prompt_dir()
    if not d:
        return None
    for item in manifest():
        if item.get("index") == index:
            p = os.path.join(d, item.get("file") or "")
            return p if os.path.exists(p) else None
    p = os.path.join(d, f"prompt_{index + 1:02d}.wav")
    return p if os.path.exists(p) else None


def load_audio(index: int):
    """(numpy-аудио, частота) для подсказки. None, если файла нет."""
    p = audio_path(index)
    if not p:
        return None
    try:
        import soundfile as sf
        data, sr = sf.read(p, dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        return data, sr
    except Exception:
        return None


def reset_cache() -> None:
    """Сбросить кэш манифеста (после копирования файлов в рабочую папку)."""
    global _MANIFEST_CACHE
    _MANIFEST_CACHE = None
