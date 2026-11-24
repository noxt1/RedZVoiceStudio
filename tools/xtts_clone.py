"""XTTS-v2: клонирование ТВОЕГО голоса для звуковой панели Auraloom.

Почему отдельный скрипт, а не tools/synthesize.py:
  coqui-tts 0.28 на Windows тянет torchaudio.load -> torchcodec -> системный FFmpeg,
  которого в системе нет. Здесь мы подменяем torchaudio.load на soundfile,
  поэтому внешних DLL не требуется.

Использование:
    python tools/xtts_clone.py --reference my_voice.wav
    python tools/xtts_clone.py --reference my_voice.wav --only 07
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prosody  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

os.environ.setdefault("COQUI_TOS_AGREED", "1")  # принять CPML для XTTS-v2

# stdout всегда UTF-8: иначе печать испанских «¡/é/ó» падает с
# UnicodeEncodeError на кодировке Windows по умолчанию (cp1251).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

XTTS_SR = 24000  # XTTS всегда выдаёт 24 кГц — это ВХОДНАЯ частота для process()


def patch_torchaudio() -> None:
    """Подменить torchaudio.load/save на soundfile (обход torchcodec/FFmpeg)."""
    import soundfile as sf
    import torch
    import torchaudio

    def _load(path, *args, **kwargs):
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        # XTTS ждёт форму [channels, samples] (как у torchaudio.load)
        return torch.from_numpy(np.ascontiguousarray(data)).unsqueeze(0), sr

    def _save(path, tensor, sample_rate, *args, **kwargs):
        arr = tensor.detach().cpu().numpy()
        if arr.ndim > 1:
            arr = arr.T
        sf.write(path, arr.astype(np.float32), sample_rate)

    torchaudio.load = _load
    torchaudio.save = _save


def norm(text: str) -> str:
    """Нормализация текста для сравнения: без диакритики, только буквы."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.lower() if ch.isalpha())


def similarity(heard: str, expected: str) -> float:
    """0..1 — насколько распознанное совпадает с ожидаемым (по набору букв)."""
    h, e = norm(heard), norm(expected)
    if not e:
        return 1.0
    if h == e:
        return 1.0
    if not h:
        return 0.0
    # доля совпавших символов (LCS-подобная метрика)
    common = 0
    pool = list(h)
    for ch in e:
        if ch in pool:
            pool.remove(ch)
            common += 1
    return common / len(e)


# Наборы параметров сэмплирования: первый — основной, дальше — запасные.
# Низкая температура даёт более чёткие короткие фразы (крики, команды).
# split_sentences=False заметно помогает на коротких выкриках вида "A huevo!".
# seed меняется, чтобы попытки не давали одинаковый результат.
# Профили сэмплирования. Чем свободнее (выше temperature/top_p/top_k),
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


def build_profiles(expressiveness: int = 2, text: str = "") -> list[dict]:
    """Профили под выбранную выразительность (0 — ровно, 3 — максимум живости).

    Если передан текст, профили подстраиваются под его ТОН: ругательство
    звучит злее и резче, вежливая фраза — теплее и мягче (tools/voice_tone.py).
    """
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
    # подстройка под тон фразы
    if text:
        profiles = _apply_tone(profiles, text)
    return profiles


def _apply_tone(profiles: list[dict], text: str) -> list[dict]:
    """Сдвинуть профили в сторону тона фразы (злой/добрый/нейтральный).

    Тон ЗАДАЁТ базу, а ползунок «Живость» добавляет разброс вокруг неё.
    Поэтому здесь не усреднение, а явный сдвиг: злой тон — выше
    temperature/top_k и чуть быстрее, добрый — ниже и мягче.
    """
    try:
        import voice_tone
        tone, params = voice_tone.describe(text)
    except Exception:
        return profiles
    if tone == "neutral":
        return profiles

    out = []
    for p in profiles:
        q = dict(p)
        cur_t = q.get("temperature", 0.75)
        cur_p = q.get("top_p", 0.85)
        cur_k = q.get("top_k", 40)
        cur_s = q.get("speed", 1.0)
        # сдвиг к «целевым» значениям тона (на 60% — тон должен быть слышен)
        q["temperature"] = round(min(1.0, cur_t * 0.4 + params["temperature"] * 0.6), 3)
        q["top_p"] = round(min(0.99, cur_p * 0.4 + params["top_p"] * 0.6), 3)
        q["top_k"] = max(1, min(100, int(round(cur_k * 0.4 + params["top_k"] * 0.6))))
        q["speed"] = round(cur_s * 0.4 + params["speed"] * 0.6, 3)
        if "repetition_penalty" in params:
            q.setdefault("repetition_penalty", params["repetition_penalty"])
        out.append(q)
    # в конце — самые выразительные (по температуре), чтобы перебор доходил
    out.sort(key=lambda p: p.get("temperature", 0.75))
    return out


SAMPLING_PROFILES = build_profiles(2)


def score_clip(similarity: float, duration: float, expected_words: int) -> float:
    """Итоговая оценка: совпадение текста минус штраф за «зацикливание».

    XTTS на коротких выкриках любит повторять фразу (и длительность в 3-6 раз
    больше нормы). Такой клип звучит хуже, чем чуть менее точный, но короткий.
    """
    ideal = 0.45 + 0.45 * expected_words  # секунды
    if ideal <= 0:
        return similarity
    ratio = duration / ideal
    if ratio <= 2.0:
        return similarity
    penalty = min(0.45, (ratio - 2.0) * 0.35)
    return max(0.0, similarity - penalty)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, help="WAV с образцом твоего голоса (6-30 сек)")
    parser.add_argument("--only", help="только один id (01, 02 ...)")
    parser.add_argument("--rms", type=float, default=-18.0)
    parser.add_argument("--out", default=os.path.join(ROOT, "out"))
    parser.add_argument("--lines", default=os.path.join(ROOT, "lines.json"))
    parser.add_argument("--attempts", type=int, default=3,
                        help="сколько раз пробовать с разными параметрами (1 = без починки)")
    parser.add_argument("--check-model", default="small",
                        help="Whisper-модель для проверки качества")
    parser.add_argument("--no-check", action="store_true",
                        help="не проверять качество, один проход")
    parser.add_argument("--texts-json", default="",
                        help="JSON со своими фразами (внимание: передача через argv ломается на кириллице)")
    parser.add_argument("--texts-file", default="",
                        help="файл с JSON со фразами (надёжнее, чем --texts-json)")
    parser.add_argument("--text", default="", help="одна фраза (с --id)")
    parser.add_argument("--id", default="01", help="id для одиночной фразы")
    parser.add_argument("--expressiveness", type=int, default=2,
                        help="выразительность интонации 0..3 (2 — по умолчанию)")
    parser.add_argument("--tone-tolerance", type=float, default=0.06,
                        help="насколько можно sacrifices точность ради выразительности")
    parser.add_argument("--lang", default="es",
                        help="язык озвучки: es, en, ow (олдвест), it")
    args = parser.parse_args()

    # Язык озвучки: XTTS-код, суффикс имени файла и поле в lines.json.
    # Испанский — основной (файлы без суффикса, чтобы не сломать ресурс
    # сервера), остальные — с суффиксом: mx_01_en.mp3 и т.п.
    try:
        import voice_lang
    except Exception:
        voice_lang = None
    if voice_lang is not None:
        lang_code = args.lang if args.lang in voice_lang.LANGS else "es"
        xtts_language = voice_lang.xtts_lang(lang_code)
        name_suffix = voice_lang.suffix(lang_code)
        lang_field = voice_lang.field(lang_code)
    else:
        lang_code, xtts_language, name_suffix, lang_field = "es", "es", "", "es"
    print(f"Язык озвучки: {lang_code} (XTTS: {xtts_language}, "
          f"суффикс: '{name_suffix}')", flush=True)

    patch_torchaudio()

    import audio_post as ap_post
    import torch
    from TTS.api import TTS

    t0 = time.time()
    model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cuda")
    print(f"Модель загружена за {time.time() - t0:.1f}с", flush=True)

    # Проверяющий Whisper: если реплика звучит не как задумано, пробуем иначе.
    verifier = None
    if not args.no_check and args.attempts > 1:
        from faster_whisper import WhisperModel
        verifier = WhisperModel(args.check_model, device="cpu", compute_type="int8")
        print(f"Проверка качества: whisper-{args.check_model}\n", flush=True)

    with open(args.lines, encoding="utf-8") as fh:
        lines = json.load(fh)["lines"]

    # Список из приложения — полный и точный: озвучиваем ровно его.
    # Раньше тут было слияние с lines.json, из-за чего часть фраз терялась.
    # JSON передаём файлом: через argv кириллица ломает разбор аргументов.
    payload_text = args.texts_json
    if args.texts_file and os.path.exists(args.texts_file):
        with open(args.texts_file, encoding="utf-8") as fh:
            payload_text = fh.read()

    if payload_text:
        try:
            custom = json.loads(payload_text)
            merged = []
            for item in custom:
                pid = str(item.get("id", "")).zfill(2)
                row = {"id": pid, "es": item.get("text", ""),
                       "text": item.get("text", ""),
                       "ru": item.get("ru", ""), "cat": item.get("cat", "custom")}
                # переводы на другие языки (если приложение их прислало)
                for key in ("en", "ow", "it"):
                    if item.get(key):
                        row[key] = item[key]
                merged.append(row)
            lines = merged
            print(f"Фраз из приложения: {len(lines)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Не разобрал список фраз: {exc}", flush=True)

    if args.text:
        lines = [{"id": args.id.zfill(2), "es": args.text, "text": args.text,
                  "ru": "", "cat": "custom"}]

    if args.only:
        lines = [l for l in lines if l["id"] == args.only.zfill(2)]

    # Текст реплики на выбранном языке: приоритет у поля языка из
    # lines.json, потом — текст, присланный приложением.
    prepared = []
    for line in lines:
        text = (line.get(lang_field) or line.get("text") or line.get("es") or "")
        prepared.append({"id": line["id"], "text": text,
                         "ru": line.get("ru", ""), "cat": line.get("cat", "")})
    lines = prepared

    def synth(text: str, profile: dict) -> np.ndarray:
        kwargs = {"split_sentences": True}
        kwargs.update(profile)  # профиль может переопределить split_sentences
        out = model.tts(
            text=text,
            speaker_wav=args.reference,
            language=xtts_language,
            **kwargs,
        )
        raw = np.asarray(out, dtype=np.float32)
        if raw.ndim > 1:
            raw = raw.mean(axis=1)
        return raw
    def check(audio: np.ndarray, expected: str) -> tuple[float, str]:
        # Whisper ждёт 16 кГц — приводим явно, иначе читает в 1.5 раза быстрее
        audio16 = ap_post.to_16k(audio, XTTS_SR)
        segs, _ = verifier.transcribe(
            audio16, language=xtts_language, beam_size=1, vad_filter=False,
            condition_on_previous_text=False,
        )
        heard = " ".join(s.text.strip() for s in segs).strip()
        words = max(1, len(expected.split()))
        duration = len(audio) / XTTS_SR
        return score_clip(similarity(heard, expected), duration, words), heard

    problems = 0
    for line in lines:
        name = f"mx_{line['id']}{name_suffix}"
        expected = line["text"]
        t0 = time.time()

        best_audio, best_score, best_heard = None, -1.0, ""
        best_tone = -1.0
        tol = max(0.0, args.tone_tolerance)

        for attempt, profile in enumerate(
                build_profiles(args.expressiveness, expected)[:max(1, args.attempts)]):
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

        processed = ap_post.process(best_audio, XTTS_SR, target_rms_db=args.rms)
        paths = ap_post.export_all(processed, args.out, name)

        flag = "OK " if best_score >= 0.999 else ("~  " if best_score >= 0.85 else "BAD")
        if flag != "OK ":
            problems += 1
        print(f"{flag}[{line['id']}] {best_score:.2f} {time.time() - t0:5.1f}s "
              f"{len(processed) / ap_post.SR:5.2f}s  {expected[:34]:<34} | {best_heard[:28]}", flush=True)

    print(f"\nГотово -> {args.out}")
    if problems:
        print(f"Требуют внимания: {problems} реплик (см. колонку score).")
        print("Перегенерируй их вручную: --only <id> --attempts 4")


if __name__ == "__main__":
    main()
