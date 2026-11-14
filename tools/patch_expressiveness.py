"""Патч: выразительная интонация в авто-починке XTTS.

Что меняется:
  * у xtts_clone.py появляется --expressiveness (0..3): чем выше, тем
    свободнее сэмплирование (temperature/top_p/top_k) -> живее интонация;
  * при выборе варианта учитывается не только разборчивость, но и разброс
    высоты тона: если вариант чуть менее точный, но заметно выразительнее —
    берём его (допуск задаётся --tone-tolerance);
  * synthesize.py (Piper) поднимает noise_scale/noise_w_scale.

    python tools\\patch_expressiveness.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLONE = os.path.join(ROOT, "tools", "xtts_clone.py")
SYNTH = os.path.join(ROOT, "tools", "synthesize.py")


def patch_clone() -> None:
    with io.open(CLONE, encoding="utf-8") as fh:
        src = fh.read()

    # 1) импорт оценки интонации
    old = "import numpy as np\n\nROOT ="
    new = "import numpy as np\n\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nimport prosody  # noqa: E402\n\nROOT ="
    if old in src:
        src = src.replace(old, new, 1)
    else:
        print("clone: точка импорта не найдена")

    # 2) профили сэмплирования, зависящие от выразительности
    old2 = '''SAMPLING_PROFILES = [
    {},
    {"temperature": 0.45, "top_p": 0.75, "top_k": 25},
    {"split_sentences": False},
    {"split_sentences": False, "temperature": 0.45, "top_p": 0.75, "top_k": 25},
    {"split_sentences": False, "temperature": 0.30, "top_p": 0.65, "top_k": 15,
     "repetition_penalty": 8.0},
    {"temperature": 0.55, "top_p": 0.80, "top_k": 35, "speed": 0.95},
    {"split_sentences": False, "temperature": 0.55, "top_p": 0.80, "top_k": 35,
     "speed": 0.92},
    {"split_sentences": False, "temperature": 0.65, "top_p": 0.85, "top_k": 40,
     "speed": 0.98},
    {"temperature": 0.40, "top_p": 0.70, "top_k": 20, "speed": 0.90},
    {"split_sentences": False, "temperature": 0.50, "top_p": 0.78, "top_k": 30,
     "speed": 1.05},
]
'''
    new2 = '''# Профили сэмплирования. Чем свободнее (выше temperature/top_p/top_k),
# тем живее интонация — но выше риск испортить фразу.
_BASE_PROFILES = [
    {},
    {"temperature": 0.45, "top_p": 0.75, "top_k": 25},
    {"split_sentences": False},
    {"split_sentences": False, "temperature": 0.45, "top_p": 0.75, "top_k": 25},
    {"split_sentences": False, "temperature": 0.30, "top_p": 0.65, "top_k": 15,
     "repetition_penalty": 8.0},
    {"temperature": 0.55, "top_p": 0.80, "top_k": 35, "speed": 0.95},
    {"split_sentences": False, "temperature": 0.55, "top_p": 0.80, "top_k": 35,
     "speed": 0.92},
    {"split_sentences": False, "temperature": 0.65, "top_p": 0.85, "top_k": 40,
     "speed": 0.98},
    {"temperature": 0.40, "top_p": 0.70, "top_k": 20, "speed": 0.90},
    {"split_sentences": False, "temperature": 0.50, "top_p": 0.78, "top_k": 30,
     "speed": 1.05},
]


def build_profiles(expressiveness: int = 2) -> list[dict]:
    """Профили под выбранную выразительность (0 — ровно, 3 — максимум живости)."""
    boost = [0.0, 0.10, 0.22, 0.38][max(0, min(3, expressiveness))]
    profiles = []
    for base in _BASE_PROFILES:
        p = dict(base)
        if boost:
            p["temperature"] = min(1.0, p.get("temperature", 0.75) + boost)
            p["top_p"] = min(0.99, p.get("top_p", 0.85) + boost * 0.25)
            p["top_k"] = min(100, int(p.get("top_k", 40) * (1 + boost)))
        profiles.append(p)
    # самые выразительные — в конце, чтобы перебор доходил до них
    profiles.sort(key=lambda p: p.get("temperature", 0.75))
    return profiles


SAMPLING_PROFILES = build_profiles(2)
'''
    if old2 in src:
        src = src.replace(old2, new2, 1)
    else:
        print("clone: SAMPLING_PROFILES не найден")

    # 3) аргументы
    old3 = '''    parser.add_argument("--id", default="01", help="id для одиночной фразы")
'''
    new3 = '''    parser.add_argument("--id", default="01", help="id для одиночной фразы")
    parser.add_argument("--expressiveness", type=int, default=2,
                        help="выразительность интонации 0..3 (2 — по умолчанию)")
    parser.add_argument("--tone-tolerance", type=float, default=0.06,
                        help="насколько можно sacrifices точность ради выразительности")
'''
    if old3 in src:
        src = src.replace(old3, new3, 1)
    else:
        print("clone: аргументы не найдены")

    # 4) выбор варианта: разборчивость + интонация
    old4 = '''        best_audio, best_score, best_heard = None, -1.0, ""

        for attempt, profile in enumerate(SAMPLING_PROFILES[:max(1, args.attempts)]):
            # Разный seed на каждую попытку — иначе все попытки дадут одно и то же.
            torch.manual_seed(1234 + attempt * 977)
            raw = synth(expected, profile)

            if verifier is None:
                best_audio, best_score, best_heard = raw, 1.0, ""
                break

            score, heard = check(raw, expected)
            if score > best_score:
                best_audio, best_score, best_heard = raw, score, heard
            if score >= 0.999:
                break
'''
    new4 = '''        best_audio, best_score, best_heard = None, -1.0, ""
        best_tone = -1.0
        tol = max(0.0, args.tone_tolerance)

        for attempt, profile in enumerate(SAMPLING_PROFILES[:max(1, args.attempts)]):
            # Разный seed на каждую попытку — иначе все попытки дадут одно и то же.
            torch.manual_seed(1234 + attempt * 977)
            raw = synth(expected, profile)

            if verifier is None:
                best_audio, best_score, best_heard = raw, 1.0, ""
                break

            score, heard = check(raw, expected)
            tone = prosody.f0_spread(raw, XTTS_SR)
            # приоритет — разборчивость; при близком качестве — выразительность
            better = score > best_score + tol
            same = abs(score - best_score) <= tol and tone > best_tone
            if better or (same and best_audio is not None):
                best_audio, best_score, best_heard = raw, score, heard
                if better:
                    best_score = score
                best_tone = tone
            elif best_audio is None:
                best_audio, best_score, best_heard = raw, score, heard
                best_tone = tone
            if score >= 0.999 and best_tone >= 22.0:
                break
'''
    if old4 in src:
        src = src.replace(old4, new4, 1)
    else:
        print("clone: блок выбора не найден")

    with io.open(CLONE, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("clone: выразительность подключена")


def patch_synth() -> None:
    with io.open(SYNTH, encoding="utf-8") as fh:
        src = fh.read()

    old = '''def synth_piper(text: str, voice: str, length_scale: float = 1.15) -> tuple[np.ndarray, int]:'''
    new = '''def synth_piper(text: str, voice: str, length_scale: float = 1.15,
                expressiveness: int = 2) -> tuple[np.ndarray, int]:'''
    if old in src:
        src = src.replace(old, new, 1)

    old2 = '''    sc = SynthesisConfig(length_scale=length_scale, noise_scale=0.55, noise_w_scale=0.8)'''
    new2 = '''    # Больше шума в фонетике/длительностях — живее интонация
    boost = [0.0, 0.06, 0.12, 0.20][max(0, min(3, expressiveness))]
    sc = SynthesisConfig(length_scale=length_scale,
                         noise_scale=min(0.95, 0.60 + boost),
                         noise_w_scale=min(1.4, 0.85 + boost * 1.5))'''
    if old2 in src:
        src = src.replace(old2, new2, 1)
    else:
        print("synth: SynthesisConfig не найден")

    old3 = '''                ls = scales.get(line["id"], 1.15)
                raw, raw_sr = synth_piper(expected, line.get("vo", "M"), ls)'''
    new3 = '''                ls = scales.get(line["id"], 1.15)
                raw, raw_sr = synth_piper(expected, line.get("vo", "M"), ls,
                                          args.expressiveness)'''
    if old3 in src:
        src = src.replace(old3, new3, 1)
    else:
        print("synth: вызов synth_piper не найден")

    old4 = '''    ap_.add_argument("--out", default=OUT)'''
    new4 = '''    ap_.add_argument("--out", default=OUT)
    ap_.add_argument("--expressiveness", type=int, default=2,
                    help="выразительность интонации 0..3 (2 — по умолчанию)")'''
    if old4 in src:
        src = src.replace(old4, new4, 1)
    else:
        print("synth: аргументы не найдены")

    with io.open(SYNTH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("synth: выразительность подключена")


if __name__ == "__main__":
    patch_clone()
    patch_synth()
