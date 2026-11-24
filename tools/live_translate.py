"""Живой перевод RU->ES: движок, который держит модели в памяти.

GUI (Auraloom.exe) не содержит torch — тяжёлые модели живут в движке
(%LOCALAPPDATA%\\Auraloom\\engine). Этот скрипт — серверная часть
живого перевода:

    -> stdin  : команды (JSON, построчно)
    <- stdout : JSON-ответы (построчно) + аудио-чанки в отдельном потоке

Протокол (одна строка JSON = одно сообщение):

  -> {"cmd": "load"}                     загрузить модели
  <- {"event": "ready", "asr_ms": ..., "tts_ms": ...}
  -> {"cmd": "speak", "text": "..."}      озвучить текст (испанский) твоим голосом
  <- {"event": "chunk", "seq": 0, "pcm": "<base64 int16 24kHz mono>"}
  <- {"event": "done", "seq": 0, "ms": 1234}
  -> {"cmd": "translate", "pcm": "<base64 int16 16kHz mono>"}
  <- {"event": "text", "ru": "...", "es": "..."}
  <- {"event": "chunk", ...} / {"event": "done", ...}
  -> {"cmd": "quit"}

Запуск:
    "<engine>\\Scripts\\python.exe" tools\\live_translate.py
"""

from __future__ import annotations

import base64
import json
import os
from collections import OrderedDict
import queue
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

SR_ASR = 16000      # частота для Whisper
SR_TTS = 24000      # XTTS всегда выдаёт 24 кГц
MT_MODEL = "Helsinki-NLP/opus-mt-ru-es"

# Языки перевода (общий модуль с приложением): es, en, ow (олдвест), it.
# Для каждого — код языка XTTS и модель перевода ru -> язык.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import voice_lang
except Exception:  # noqa: BLE001
    voice_lang = None

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import model_registry as mreg
except Exception:  # noqa: BLE001
    mreg = None

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import glossary as glos
except Exception:  # noqa: BLE001
    glos = None


def _lang_info(code: str) -> dict:
    """Параметры языка (если модуль недоступен — только испанский)."""
    if voice_lang is None:
        return {"title": "Испанский", "xtts": "es",
                "mt": ["Helsinki-NLP/opus-mt-ru-es"], "field": "es"}
    return voice_lang.info(code)


def _rss_mb() -> float:
    """Сколько RAM занято процессом (МБ) — для диагностики крашей."""
    try:
        import ctypes
        class _Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32),
                        ("PageFaultCount", ctypes.c_uint32),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        pid = ctypes.windll.kernel32.GetCurrentProcessId()
        h = ctypes.windll.kernel32.OpenProcess(0x400, False, pid)
        if not h:
            return 0.0
        try:
            ctypes.windll.psapi.GetProcessMemoryInfo(
                h, ctypes.byref(counters), counters.cb)
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
        return counters.WorkingSetSize / (1024.0 * 1024.0)
    except Exception:
        return 0.0


def _mt_names(code: str) -> list[str]:
    """Список моделей перевода ru -> язык (одна или цепочка)."""
    if voice_lang is None:
        return ["Helsinki-NLP/opus-mt-ru-es"]
    return voice_lang.mt_model(code)


def _reverse_mt_names(src: str) -> list[str]:
    """Список моделей перевода язык -> русский."""
    if voice_lang is None:
        return []
    return voice_lang.reverse_mt(src)


def xtts_language(code: str) -> str:
    """Код языка для XTTS."""
    return _lang_info(code)["xtts"]


# Модель распознавания.
# Замер (research/bench_asr_models.py, образцы пользователя, RTX 5080):
#   Systran/faster-whisper-small        ~79 мс, БЕЗ знаков препинания,
#                                       теряет слова («не фигня, брат» ->
#                                       «не фигня обратно»)
#   large-v3-turbo                      ~108 мс, С ЗНАКАМИ ПРЕПИНАНИЯ и полными
#                                       фразами — текст заметно лучше
# Разница по скорости всего ~30 мс, а качество текста критично: от него
# зависит перевод. Поэтому по умолчанию — turbo.
ASR_MODEL = os.environ.get("AURALOOM_ASR_MODEL", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
ASR_FALLBACK = os.environ.get("AURALOOM_ASR_FALLBACK", "Systran/faster-whisper-small")

# Точность вычислений для распознавания:
#   float16      — VRAM 2241 МБ
#   int8_float16 — тот же текст на записях пользователя, VRAM 1019 МБ
#                  (минус ~1.2 ГБ — важно, когда параллельно игра)
# Замер: research/bench_optimization.py, research/bench_int8_quality.py
ASR_COMPUTE = os.environ.get("AURALOOM_ASR_COMPUTE", "int8_float16")

# Минимальная уверенность определения языка собеседника (режим auto).
# Ниже порога фраза не переводится: лучше пропустить, чем озвучить не то.
PEER_LANG_MIN_CONF = float(os.environ.get("AURALOOM_PEER_LANG_CONF", "0.60"))
# Сколько цепочек перевода держать в памяти: 2 — переключение языка
# мгновенное, но +~600 МБ RAM; 1 — экономно, с перезагрузкой модели.
MT_CACHE_CHAINS = max(1, int(os.environ.get("AURALOOM_MT_CACHE_CHAINS", "2")))
# Замер на 12 реальных фразах (build/quality_sweep): для обратного перевода
# (собеседник -> RU) beam=4 дал chrF 36,9 против 30,7 у greedy, ценой
# +150 мс — там это не критично. Для прямого (RU -> ES) greedy лучше
# (41,6 против 37,8), поэтому beam включается только для обратного.
MT_BEAMS_REVERSE = max(1, int(os.environ.get("AURALOOM_MT_BEAMS_REVERSE", "4")))
# Исходящий перевод: по замеру greedy точнее (chrF 41,6 против 37,8
# у beam=4) и втрое быстрее. Стабильность фразы обеспечивается кэшем и
# самим ASR; увеличение beam калечит качество — не трогаем.
MT_BEAMS_FORWARD = max(1, int(os.environ.get("AURALOOM_MT_BEAMS_FORWARD", "1")))

# Недосклеенные куски реплики собеседника не должны ждать последнюю часть
# вечно: если последний кусок потерялся (переполнение очереди, обрыв записи
# в stdin движка), остаток приклеивался к СЛЕДУЮЩЕЙ фразе, и две разные
# реплики уходили в распознавание как одна. Основной признак — номер фразы
# (GUI нумерует каждую отправленную реплику), таймаут и ограничение объёма —
# страховка для источника без номера.
PEER_PARTS_TTL = max(1.0, float(os.environ.get("AURALOOM_PEER_PARTS_TTL", "8")))
PEER_PARTS_MAX_BYTES = int(os.environ.get("AURALOOM_PEER_PARTS_MAX", "2000000"))

# Версия протокола GUI <-> движок. Меняется при любом изменении полей
# команд/событий: GUI сравнивает её с boot-событием и предупреждает,
# если рядом работает движок от другой сборки (частый случай — старый
# процесс движка после обновления EXE: фиксы не доезжают, а ошибок нет).
# Писать ли распознанный/переведённый текст в лог строками [mt]. По
# умолчанию выключено (это содержимое разговора); включается на время
# разбора: set AURALOOM_LOG_MT_TEXT=1.
MT_LOG_TEXT = os.environ.get("AURALOOM_LOG_MT_TEXT", "") not in (
    "", "0", "false", "False")

PROTOCOL_VERSION = 3

# Почему фраза собеседника осталась без перевода (счётчики для отчёта).
SKIP_REASONS = {
    "empty": "распознавание пустое",
    "no_speech": "тишина/шум",
    "hallucination": "фильтр галлюцинаций",
    "lang": "язык не подтверждён",
    "no_mt": "нет модели перевода",
    "empty_ru": "перевод пустой",
    "own_voice": "свой голос (эхо в захвате)",
    "duplicate": "повтор уже переведённой фразы",
}


def _hf_hub_dir() -> str:
    """Каталог кэша HuggingFace (оттуда движок берёт модели)."""
    return os.environ.get("HF_HUB_CACHE") or os.path.expanduser(
        os.path.join("~", ".cache", "huggingface", "hub"))


def _ref_sig(path: str) -> tuple:
    """Подпись reference: путь + mtime + размер.

    Без mtime повторная сборка reference по тому же пути считалась
    «уже загруженной», и клонированный голос не менялся.
    """
    try:
        st = os.stat(path)
        return (os.path.normcase(os.path.abspath(path)),
                getattr(st, "st_mtime_ns", 0), st.st_size)
    except Exception:
        return ("", 0, 0)


def _model_installed(name) -> bool:
    """Есть ли модель уже на диске. Ничего не скачивает."""
    if not name:
        return False
    name = _chain_name(name)
    if os.path.isdir(name):          # локальная папка с моделью
        try:
            return bool(os.listdir(name))
        except Exception:
            return False
    base = os.path.join(_hf_hub_dir(), "models--" + name.replace("/", "--"))
    try:
        snaps = os.path.join(base, "snapshots")
        return os.path.isdir(base) and bool(os.listdir(snaps))
    except Exception:
        return False


def _chain_name(item) -> str:
    """Имя модели из элемента цепочки (строка или (имя, target-токен))."""
    return item[0] if isinstance(item, (list, tuple)) else item


def _asr_candidates() -> list[str]:
    """Установленные модели распознавания: env-имена + всё в кэше."""
    names = [ASR_MODEL, ASR_FALLBACK]
    try:
        for entry in os.listdir(_hf_hub_dir()):
            if entry.startswith("models--") and "faster-whisper" in entry:
                names.append(entry[len("models--"):].replace("--", "/"))
    except Exception:
        pass
    out: list[str] = []
    for name in names:
        if name and name not in out and _model_installed(name):
            out.append(name)
    return out

# Перевод на CPU: он занимает 0.6 ГБ VRAM и совсем немного GPU.
# Разница по скорости — 147 мс против 77 мс, зато видеопамять вся
# остаётся игре и XTTS.
MT_DEVICE = os.environ.get("AURALOOM_MT_DEVICE", "cpu")

# ---------------------------------------------------------------------------
# Режимы Fast / Balanced / Quality / Manual.
#
# Режим меняет ТОЛЬКО уже установленные модели и параметры декодирования:
# ничего не скачивается. Если вариант один, это видно в mode_info
# (asr_alternatives), а не заменяется выдуманной альтернативой.
# ---------------------------------------------------------------------------
MODES: dict[str, dict] = {
    "fast": {
        "title": "Fast",
        "compute": "int8_float16",
        "beam": 1,
        "stream_chunk": 20,
        "verify": 0,
        # короткие фразы тоже отдаём по мере синтеза (без проверки)
        "stream_short": True,
        "mt_device": "cpu",
    },
    "balanced": {
        "title": "Balanced",
        "compute": "int8_float16",
        "beam": 1,
        "stream_chunk": 30,
        "verify": 1,
        # Замер: стриминг короткой фразы — 481 мс до первого звука
        # вместо 1111 мс при полном синтезе с проверкой.
        "stream_short": True,
        "mt_device": "cpu",
    },
    "quality": {
        "title": "Quality",
        # Замер out/probe_vram_models.py (22.11): float16 занимает 2221 МБ
        # VRAM, int8_float16 — 1209 МБ при том же тексте на записях
        # пользователя (research/bench_int8_quality.py). Режим Quality
        # отличается beam/проверками, а не точностью ASR.
        "compute": "int8_float16",
        "beam": 3,
        "stream_chunk": 40,
        "verify": 2,
        "stream_short": False,
        "mt_device": "cpu",
    },
    "manual": {
        "title": "Manual",
        "compute": "int8_float16",
        "beam": 1,
        "stream_chunk": 30,
        "verify": 1,
        "stream_short": False,
        "mt_device": "cpu",
    },
}

# Размер чанка XTTS: чем меньше, тем раньше появляется первый звук.
# Важно, когда GPU занят игрой.
#
# Правка Этап C.7.2: было 10 — XTTS выдавал фразы «обрывками»: на стыке
# чанков пропадали слоги, слова не договаривались. 30 даёт связную речь
# с приемлемой задержкой (первый звук ~на 200 мс позже, чем при 10).
STREAM_CHUNK = int(os.environ.get("AURALOOM_STREAM_CHUNK", "30"))

# Сколько секунд синтеза слушать, прежде чем признать начало годным.
# Мусор на коротких фразах слышен сразу, поэтому ждать всю фразу не нужно
# (иначе первый звук задерживается на лишние ~1 с).
PREFIX_CHECK_SEC = 0.3


def _tone_params(text: str, ru: str = "", liveliness: int = 2) -> tuple[str, dict]:
    """Тон фразы -> параметры синтеза XTTS (злее/добрее).

    Тон определяется по РУССКОМУ тексту (что реально сказал игрок):
    перевод смягчает эмоцию («Вы ссаны ублюдки!» -> «¿Qué tal mi juego?»),
    и по испанскому её уже не поймать.

    liveliness — уровень от пользователя (0 — ровно, 3 — максимум): чем
    выше, тем свободнее сэмплирование и разнообразнее интонация.
    ВАЖНО: выше temperature=0.85 XTTS начинает «говорить кашей» —
    при 0.95 разборчивость падает до 12%. Поэтому потолок жёсткий.

    Модуль voice_tone лежит рядом (tools/). В EXE он тоже попадает в бандл.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import voice_tone
        tone = voice_tone.detect_tone_pair(ru, text) if ru else \
            voice_tone.detect_tone(text)
        params = dict(voice_tone.params_for_tone(tone))
        # Уровень живости сдвигает параметры, но не ломает потолок.
        # ВАЖНО: repetition_penalty НЕ понижаем — его снижение (до 3-5)
        # заставляет XTTS тараторить и зацикливаться. Держим 10 (дефолт).
        level = max(0, min(3, int(liveliness)))
        boost = (level - 2) * 0.03
        params["temperature"] = round(min(0.82,
                                         params.get("temperature", 0.79) + boost), 3)
        params["top_p"] = round(min(0.92,
                                    params.get("top_p", 0.88) + boost * 0.2), 3)
        params["top_k"] = max(1, min(80, int(params.get("top_k", 55)
                                          * (1 + boost))))
        # ТЕМП: держим 0.93-1.0. Выше 1.0 XTTS «тараторит» и глотает
        # согласные; ниже 0.92 — вяло и монотонно.
        params["speed"] = round(min(1.0, max(0.93,
                                            params.get("speed", 0.96) + boost * 0.15)), 3)
        # repetition_penalty держим высоким (дефолт XTTS = 10): ниже 8
        # модель начинает спешить и повторять слова.
        params["repetition_penalty"] = 10.0
        # top_k/top_p XTTS не принимает 0 — подстраховка
        params["top_k"] = max(1, int(params.get("top_k", 50)))
        params["top_p"] = min(0.99, max(0.01, float(params.get("top_p", 0.86))))
        return tone, params
    except Exception as exc:  # noqa: BLE001
        log(f"[engine] тон не определён ({type(exc).__name__}: {exc})")
        return "neutral", {"temperature": 0.75, "top_p": 0.86, "top_k": 50,
                           "speed": 1.02, "repetition_penalty": 5.0}


# Знаки, которые снимаем с краёв слова при сравнении повторов и имён.
_PUNCT = ".,!?;:¿¡…—–\"'()"


def _cyrillic_share(text: str) -> float:
    """Доля кириллицы среди букв (для проверки «это правда русский?»)."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
    return cyr / len(letters)


def _repeated_ngram(text: str, n_min: int = 3, n_max: int = 4,
                    limit: int = 3, min_words: int = 10) -> bool:
    """Есть ли в ДЛИННОМ тексте n-грамма, повторённая `limit` раз.

    На шуме/обрывках записи Whisper уходит в цикл и выдаёт одно и то же
    («...you're all the seasons and you're all the seasons and you're all
    the seasons»). Такой текст переводился дословно, и собеседник слышал
    бессмыслицу, поэтому его надо отбрасывать как галлюцинацию.

    Фразы из одного и того же повтора («Боже мой, Боже мой, Боже мой!»,
    «Vete a la mierda» три раза) — живая речь, а не цикл: у цикла повтор
    занимает только часть длинной фразы, поэтому требуем ещё и «хвост».
    """
    # Пунктуация не должна различать слова: «caballo?» и «caballo» —
    # один и тот же повтор, иначе цикл с разными знаками не ловится.
    words = [w.strip(_PUNCT) for w in text.split()]
    words = [w for w in words if w]
    if len(words) < max(min_words, limit * n_min):
        return False
    for n in range(n_min, n_max + 1):
        seen: dict = {}
        for i in range(len(words) - n + 1):
            gram = tuple(words[i:i + n])
            seen[gram] = seen.get(gram, 0) + 1
            if seen[gram] >= limit and seen[gram] * n <= 0.6 * len(words):
                return True
    return False


# Известные ослышки имён в распознанной речи. Правим ТЕКСТ, а не
# подсказку декодеру: замер (out/probe_hw_halluc.py) показал, что hotwords
# из глоссария на не-речи (белый шум, розовый шум, цифровая тишина) дают
# 3 из 3 «de Linde, Blackwater, Saint Denis, Valentine…» — ровно тот бред,
# который владелец слышал из фона. Без подсказки — 0 из 3. Замена ниже
# требует точного совпадения слов, поэтому имя в шуме выдумать не может.
_ASR_NAME_FIXES = (
    (("mars", "al"), "Marshall"),
    (("marsal",), "Marshall"),
)


def fix_asr_names(text: str) -> str:
    """Починить известные ослышки имён («Mars al» -> «Marshall»)."""
    if not text:
        return text
    tokens = text.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        hit = False
        for keys, name in _ASR_NAME_FIXES:
            n = len(keys)
            if i + n > len(tokens):
                continue
            chunk = [t.strip(_PUNCT).lower() for t in tokens[i:i + n]]
            if chunk != list(keys):
                continue
            last = tokens[i + n - 1]
            tail = ""
            while last and last[-1] in _PUNCT:
                tail = last[-1] + tail
                last = last[:-1]
            out.append(name + tail)
            i += n
            hit = True
            break
        if not hit:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


# Заготовки Whisper из обучающих субтитров: на шуме модель «прощается со
# зрителем» («We'll see you next time»). Проверяем только короткий текст,
# чтобы не выбросить живую фразу, где эти слова стоят рядом с другими.
_BOILERPLATE = (
    "see you next time", "see you in the next video",
    "thanks for watching", "thank you for watching",
    "like and subscribe", "subscribe to my channel",
)

# Мычание и вздохи: смысла в них нет, а в переводе из них получается «Угу»,
# которое уходит в озвучку.
_FILLERS = frozenset((
    "mm", "mmm", "mmmm", "mm-mm", "mm-hmm", "mmhmm", "mhm", "hm", "hmm",
    "uh", "uh-huh", "um", "erm",
))


def _is_filler(text: str) -> bool:
    """Текст — только мычание/вздохи («Mm-mm», «Hmm»)."""
    words = [w.strip(_PUNCT).lower() for w in text.split()]
    words = [w for w in words if w]
    return bool(words) and len(words) <= 3 and all(w in _FILLERS for w in words)


def _pure_repetition(text: str, max_words: int = 8,
                     min_reps: int = 4) -> bool:
    """Весь короткий текст — один и тот же повтор 4+ раза.

    Реальные галлюцинации из фона: «Look, look, look, look, look, look.»
    (в переводе «Смотри, смотри, смотри…»), «Apres, apres, apres…»,
    «Watch out, watch out, watch out, watch out.». Это цикл декодера, а не
    речь: живой человек повторяет фразу 2–3 раза, и рядом обычно есть
    другие слова («Vete a la mierda» x3, «Пошёл нахуй» x3), а тут весь
    сегмент — один и тот же повтор.
    """
    words = [w.strip(_PUNCT).lower() for w in text.split()]
    words = [w for w in words if w]
    if not words or len(words) > max_words:
        return False
    for n in (1, 2):
        if len(words) % n:
            continue
        if len(words) // n < min_reps:
            continue
        gram = words[:n]
        if all(words[i:i + n] == gram for i in range(0, len(words), n)):
            return True
    return False


def is_hallucination(text: str) -> bool:
    """Похоже ли это на галлюцинацию Whisper (текст из тишины/шума)?

    Whisper на шуме и тишине выдаёт заготовки: «Субтитры сделал…»,
    «Продолжение следует…», «Спасибо за просмотр» и т.п., а на обрывках
    речи — зацикленные повторы. Их озвучивать нельзя.
    """
    if not text:
        return True
    low = text.lower().strip()
    if len(low) < 4:
        return True
    markers = (
        "субтитры", "продолжение следует", "спасибо за просмотр",
        "дimaторзок", "dimatorzok", "субтитры сделал", "www.", "http",
        "thanks for watching", "gracias por ver", "подписывайтесь",
        "лайк", "комментарий",
        "постарше", "мне нужно", "ты не знаешь", "я не знаю, что это",
        "пожалуйста, послушайте", "кхм",
    )
    if any(m in low for m in markers):
        return True
    if len(low.split()) <= 6 and any(b in low for b in _BOILERPLATE):
        return True
    if _is_filler(low) or _pure_repetition(low):
        return True
    return _repeated_ngram(low)


_emit_lock = threading.Lock()


def emit(obj: dict) -> None:
    """Отправить JSON-строку в stdout (и сразу.flush — GUI ждёт построчно).

    Потокобезопасно: используется глобальная блокировка, чтобы чанки
    входящего TTS (из рабочего потока) не перемешивались с ответами
    из главного цикла IPC.
    """
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with _emit_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


LOG_FILE = None


def log(msg: str) -> None:
    """Служебное сообщение: в stderr И в файл (в EXE консоли нет)."""
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass


class _TtsHold:
    """Захват защёлки XTTS на время блока (для `with`)."""

    def __init__(self, gate: "_TtsGate", priority: int) -> None:
        self._gate = gate
        self._priority = priority

    def __enter__(self) -> "_TtsHold":
        self._gate.acquire(self._priority)
        return self

    def __exit__(self, *exc) -> bool:
        self._gate.release()
        return False


class _TtsGate:
    """Защёлка XTTS с приоритетом: своя речь не ждёт очередь входящих фраз.

    XTTS — одна модель в памяти и не потокобезопасна, поэтому синтез всё
    равно идёт по одному. Но входящая (русская) озвучка обрабатывается
    очередью из нескольких фраз, и обычный `threading.Lock` не гарантирует
    порядок: после освобождения замка следующая входящая фраза могла
    проскочить раньше исходящего перевода, и своя речь ждала ещё несколько
    фраз.

    Здесь ожидающие делятся на два класса: PRIO_OUT — исходящий перевод
    (то, что сказал пользователь) и пересборка голоса; PRIO_IN — входящая
    озвучка в наушники. Входящая не захватывает замок, пока ждёт хоть один
    исходящий. Ждать приходится только остаток фразы, которая уже
    синтезируется, а не всю очередь.
    """

    PRIO_OUT = 0
    PRIO_IN = 1

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._busy = False
        self._waiting = [0, 0]
        # Сколько последний acquire ждал — по потоку, для строки таймингов.
        self._tls = threading.local()

    def acquire(self, priority: int = PRIO_OUT) -> None:
        t0 = time.perf_counter()
        with self._cond:
            self._waiting[priority] += 1
            try:
                while self._busy or any(self._waiting[p]
                                        for p in range(priority)):
                    self._cond.wait()
                self._busy = True
            finally:
                self._waiting[priority] -= 1
        self._tls.wait_ms = int((time.perf_counter() - t0) * 1000)

    @property
    def wait_ms(self) -> int:
        """Сколько ТЕКУЩИЙ поток ждал замок при последнем захвате."""
        return int(getattr(self._tls, "wait_ms", 0))

    def release(self) -> None:
        with self._cond:
            self._busy = False
            self._cond.notify_all()

    def hold(self, priority: int = PRIO_IN) -> _TtsHold:
        """Захватить замок на время блока с указанным приоритетом."""
        return _TtsHold(self, priority)

    def __enter__(self) -> "_TtsGate":
        # Обычный `with self.lock` — это исходящий синтез/пересборка голоса.
        self.acquire(self.PRIO_OUT)
        return self

    def __exit__(self, *exc) -> bool:
        self.release()
        return False


class Engine:
    """Модели и логика перевода. Загружаются один раз и живут в памяти."""

    def __init__(self) -> None:
        self.asr = None
        # Имя загруженной модели распознавания (для выбора в интерфейсе).
        self.asr_model = ""
        self.mt_tok = None
        self.mt = None
        self.tts = None
        self.gpt_latent = None
        self.spk_emb = None
        # XTTS один на оба направления; замок с приоритетом, чтобы
        # исходящий перевод не стоял за очередью входящих фраз.
        self.lock = _TtsGate()
        self.load_ms = 0
        # Уровень живости (0 — ровно, 3 — максимум). Пользователь задаёт
        # ползунком; тон фразы сдвигает параметры поверх него.
        self.liveliness = 2
        # Язык перевода: es (по умолчанию), en, ow (олдвест), it, mg (мегрельский)
        self.lang = "es"
        # Язык, на котором говорит пользователь (источник исходящего перевода).
        # Сейчас надёжно поддержан только русский: MT-веса ru->X уже есть, а
        # X->ru требует отдельной модели (появится после установки пакета).
        self.src_lang = "ru"
        # Кэш моделей перевода: код -> (токенизатор, модель).
        # Держим не больше двух (текущий + испанский), чтобы не съедать RAM.
        self._mt_cache: dict[str, list] = {}
        # Кэш готовых переводов (ROADMAP 4.5): повторная фраза не гоняет
        # модель заново. Ключ — (направление, язык, текст), значение — перевод.
        self._text_cache: "OrderedDict[tuple, str]" = OrderedDict()
        self._text_cache_max = 512
        self._text_cache_lock = threading.Lock()
        self.cache_hits = 0
        self.cache_misses = 0
        # Глоссарий терминов (ROADMAP 4.6–4.7); загружается лениво.
        self.glossary = None
        # Piper-озвучка для языков, которых нет в XTTS (например, грузинский).
        # Кэш: путь к .onnx -> PiperVoice
        self._piper_cache: dict[str, object] = {}
        # ---------- перехват речи других игроков ----------
        self._peer_q: "queue.Queue" = queue.Queue(maxsize=8)
        self._peer_thread: threading.Thread | None = None
        # Куски одной длинной фразы собеседника (транспорт из GUI):
        # склеиваются обратно ДО распознавания, иначе каждые 5 с
        # переводились как отдельные реплики без контекста.
        self._peer_parts: list[bytes] = []
        self._peer_parts_id: int | None = None   # номер незаконченной фразы
        self._peer_parts_at = 0.0                # когда получен первый кусок
        # Очередь входящего синтеза: голос один (XTTS), поэтому фразы
        # озвучиваются строго по очереди, а не параллельными потоками.
        self._incoming_jobs: list[tuple] = []
        self._incoming_jobs_lock = threading.Lock()
        self._incoming_worker_on = False
        # Язык чужой речи: "auto" (определяем сами) или es/en/it/ru
        self.peer_lang = "auto"
        # Автоскачивание недостающих пакетов перевода — ВЫКЛЮЧЕНО по умолчанию.
        # Включается только пользователем в настройках приложения.
        self.auto_download = False
        self._downloaded: set[str] = set()
        # Управление моделями (Model Manager).
        self.loaded = False
        self.reference = ""
        self._reference_sig: tuple = ("", 0, 0)
        self._cancel_requests: set[str] = set()
        self._download_ids: set[str] = set()
        self._chain_repos: dict[str, list[str]] = {}
        # Подтверждённый язык собеседника (режим auto, фаза 4).
        self.peer_lang_confirmed = ""
        self._lang_hits: list[tuple[str, float]] = []
        self._peer_lang_prob = 0.0
        self._peer_lang_min_sec = float(
            os.environ.get("AURALOOM_PEER_LANG_MIN_SEC", "1.1"))
        self._peer_lang_min_words = int(
            os.environ.get("AURALOOM_PEER_LANG_MIN_WORDS", "2"))
        # ---------- режим работы и метрики ----------
        self.mode = "balanced"
        self.asr_compute = ASR_COMPUTE
        self.beam_size = 1
        self.stream_chunk = STREAM_CHUNK
        self.verify_attempts = 1
        # Стримить и короткие фразы (без полного синтеза и проверки).
        # Включается режимом Fast/Balanced: первый звук приходит раньше,
        # но проверка распознаванием для этих фраз не выполняется.
        self.stream_short = True
        self.mt_device = MT_DEVICE
        # Поколение результатов: растёт при любой смене настроек, старые
        # результаты после неё отбрасываются (generation guards).
        self.gen = 0
        self._last_translated = ""
        self._peer_seq = 0
        self.dropped = 0
        self.cancelled = 0
        # Фразы, которые были, но остались без перевода: причина -> счётчик.
        self.skipped: dict[str, int] = {key: 0 for key in SKIP_REASONS}
        # Причина последнего пустого результата transcribe_peer (для счётчиков).
        self._asr_skip = ""
        # Ожидают озвучки: тайминги ASR/MT для строки «фраза целиком».
        self._pending_timings: list[dict] = []
        self.diagnostics = None
        # Последнее, что мы САМИ сказали в игру — по нему отсекаем
        # собственный голос, попавший в перехват из наушников.
        self.last_spoken: list[str] = []

    # ---------- загрузка ----------
    def load(self, reference: str) -> None:
        import torch
        self.reference = reference or self.reference
        from faster_whisper import WhisperModel
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        t0 = time.time()
        # распознавание: пробуем лёгкую модель, при неудаче — тяжёлую
        # ASR_COMPUTE: float16 (качество) или int8_float16 (экономия VRAM).
        # Замер: int8_float16 даёт тот же текст, но VRAM 2241 -> 1019 МБ
        # и распознавание в ~2.4 раза быстрее.
        self.asr = None
        ordered = [self._pick_asr(self.mode)] + [ASR_MODEL, ASR_FALLBACK]
        for name in ordered:
            if not name or not _model_installed(name):
                continue
            try:
                self.asr = WhisperModel(name, device="cuda",
                                        compute_type=self.asr_compute)
                self.asr_model = name
                log(f"[engine] распознавание: {name} ({self.asr_compute})")
                break
            except Exception as exc:  # noqa: BLE001
                log(f"[engine] не удалось загрузить {name}: {exc}")
        if self.asr is None:
            raise RuntimeError("не удалось загрузить модель распознавания")

        # перевод: по умолчанию на CPU — освобождаем видеопамять для игры
        self._mt_for(self.lang)
        self.load_ms = int((time.time() - t0) * 1000)
        self.loaded = True
        log(f"[engine] ASR + перевод загружены за {self.load_ms} мс "
            f"(перевод на {MT_DEVICE})")

        # Поток перехвата чужой речи (стартует сразу, но звук приходит
        # только когда приложение его присылает).
        if self._peer_thread is None:
            self._peer_thread = threading.Thread(target=self._peer_loop,
                                                 daemon=True)
            self._peer_thread.start()

        self._load_tts(reference)

    # ---------- выбор моделей ----------
    def models_info(self) -> dict:
        """Что реально установлено на диске (без скачивания).

        Интерфейс показывает только это: один вариант — значит один, без
        фиктивных переключателей.
        """
        asr = [{"name": n, "active": n == self.asr_model}
               for n in _asr_candidates()]
        xtts = _model_installed("tts-hub/XTTS-v2")
        mt = []
        for code in ("es", "en", "ow", "it"):
            chain = _mt_names(code)
            mt.append({
                "pair": f"ru->{code}",
                "models": [_chain_name(i) for i in chain],
                "installed": bool(chain) and all(
                    _model_installed(_chain_name(i)) for i in chain),
            })
        for src in ("es", "en", "it"):
            chain = _reverse_mt_names(src)
            mt.append({
                "pair": f"{src}->ru",
                "models": [_chain_name(i) for i in chain],
                "installed": bool(chain) and all(
                    _model_installed(_chain_name(i)) for i in chain),
            })
        return {
            "asr": asr,
            "asr_current": self.asr_model,
            "tts": [{"name": "XTTS v2 (клон голоса)", "installed": bool(xtts)}],
            "tts_current": "XTTS v2 (клон голоса)",
            "mt": mt,
            "auto_download": self.auto_download,
            "src_languages": self.src_languages(),
            "src_current": self.src_lang,
        }

    def src_languages(self) -> list[dict]:
        """Языки, с которых можно переводить на выбранный язык."""
        out = [{"code": "ru", "name": "Русский", "installed": True}]
        for code in ("es", "en", "it"):
            if self.reverse_available(code):
                info = _lang_info(code)
                out.append({"code": code, "name": info["title"],
                            "installed": True})
        return out

    def set_src_lang(self, code: str) -> str:
        """Язык пользователя (источник исходящего перевода)."""
        code = (code or "").lower().strip()
        allowed = {item["code"] for item in self.src_languages()}
        if code not in allowed:
            log(f"[engine] язык пользователя {code!r} не поддержан "
                f"(доступны: {sorted(allowed)})")
            return self.src_lang
        self.src_lang = code
        log(f"[engine] язык пользователя: {code}")
        return self.src_lang

    # ---------- режимы работы ----------
    def _pick_asr(self, mode: str) -> str:
        """Самая быстрая/качественная ИЗ УСТАНОВЛЕННЫХ ASR-модель."""
        avail = _asr_candidates()
        if not avail:
            return ""
        if mode == "fast":
            return next((n for n in avail if "small" in n), avail[0])
        return next((n for n in avail
                     if "turbo" in n or "large" in n), avail[0])

    def stats(self) -> dict:
        """Диагностика: RAM/VRAM, очереди, счётчики отмен/потерь."""
        vram = 0.0
        try:
            import torch
            if torch.cuda.is_available():
                vram = torch.cuda.memory_reserved() / (1024.0 * 1024.0)
        except Exception:
            pass
        return {
            "rss_mb": round(_rss_mb(), 1),
            "vram_mb": round(vram, 1),
            "queues": {"peer": self._peer_q.qsize()},
            "dropped": self.dropped,
            "cancelled": self.cancelled,
            "skipped": dict(self.skipped),
            "protocol": PROTOCOL_VERSION,
            "gen": self.gen,
            "mode": self.mode,
            "loaded": self.loaded,
        }

    def _peer_skip(self, reason: str, detail: str = "") -> None:
        """Учесть фразу, которая была, но осталась без перевода."""
        reason = reason if reason in SKIP_REASONS else "empty"
        self.skipped[reason] = self.skipped.get(reason, 0) + 1
        log(f"[engine] фраза без перевода: {SKIP_REASONS[reason]}"
            f" ({detail or '—'}; всего {self.skipped[reason]})")
        emit({"event": "peer_skip", "reason": reason,
              "label": SKIP_REASONS[reason], "detail": detail,
              "counts": dict(self.skipped)})

    def _bump_gen(self, reason: str) -> None:
        """Новое поколение результатов: старые уже не нужны."""
        self.gen += 1
        log(f"[engine] поколение {self.gen} ({reason})")

    def mode_info(self) -> dict:
        avail = _asr_candidates()
        return {
            "mode": self.mode,
            "title": MODES.get(self.mode, MODES["balanced"])["title"],
            "asr_model": self.asr_model,
            "asr_compute": self.asr_compute,
            "beam_size": self.beam_size,
            "stream_chunk": self.stream_chunk,
            "verify_attempts": self.verify_attempts,
            "stream_short": self.stream_short,
            "mt_device": self.mt_device,
            "asr_alternatives": len(avail),
            "tts_alternatives": 1,
            "mt_note": "направление задаётся языком, не режимом",
        }

    def set_mode(self, code: str) -> dict:
        """Применить режим Fast / Balanced / Quality / Manual.

        Меняет только установленные модели и параметры декодирования:
        ничего не скачивает. Manual — ручной выбор, режим ничего не
        переопределяет.
        """
        code = (code or "").strip().lower()
        if code not in MODES:
            code = "balanced"
        self.mode = code
        if code != "manual":
            conf = MODES[code]
            self.asr_compute = conf["compute"]
            self.beam_size = int(conf["beam"])
            self.stream_chunk = int(conf["stream_chunk"])
            self.verify_attempts = int(conf["verify"])
            self.stream_short = bool(conf.get("stream_short", False))
            if conf["mt_device"] != self.mt_device:
                self.mt_device = conf["mt_device"]
                self._clear_mt_cache()
            target = self._pick_asr(code)
            # до загрузки движка ASR не трогаем: параметры применятся
            # при старте, лишние секунды не тратятся
            active = self.asr is not None or self.loaded
            if active and target and (target != self.asr_model
                           or self.asr_compute != getattr(self, "_asr_loaded_with",
                                                          self.asr_compute)):
                try:
                    self._switch_asr(target, self.asr_compute)
                except Exception as exc:  # noqa: BLE001
                    log(f"[engine] режим {code}: ASR не переключена "
                        f"({type(exc).__name__}: {exc})")
        self._bump_gen(f"режим {code}")
        info = self.mode_info()
        log(f"[engine] режим: {info['title']} — ASR {info['asr_model']} "
            f"({info['asr_compute']}, beam {info['beam_size']}), "
            f"TTS chunk {info['stream_chunk']}, проверок {info['verify_attempts']}, "
            f"стриминг коротких: {'да' if info['stream_short'] else 'нет'}")
        emit({"event": "mode", **info})
        return info

    def _switch_asr(self, name: str, compute: str | None = None) -> str:
        """Загрузить другую установленную ASR-модель."""
        name = (name or "").strip()
        compute = compute or self.asr_compute
        if not name or not _model_installed(name):
            raise RuntimeError(f"модель не установлена: {name}")
        if name == self.asr_model and compute == getattr(
                self, "_asr_loaded_with", self.asr_compute):
            return self.asr_model
        from faster_whisper import WhisperModel
        log(f"[engine] смена ASR: {self.asr_model} -> {name} ({compute})")
        t0 = time.time()
        new = WhisperModel(name, device="cuda", compute_type=compute)
        old = self.asr
        self.asr = new
        self.asr_model = name
        self.asr_compute = compute
        self._asr_loaded_with = compute
        try:
            del old
            import gc
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        log(f"[engine] ASR переключена на {name} за "
            f"{int((time.time() - t0) * 1000)} мс")
        return self.asr_model

    def set_asr(self, name: str) -> str:
        """Переключить модель распознавания (ручной выбор, Manual)."""
        return self._switch_asr(name, self.asr_compute)

    # ---------- каталог и управление моделями ----------
    REQUIRED_FILES = {
        "asr": ("model.bin", "config.json"),
        "tts": ("config.json", "model.pth", "vocab.json"),
        "mt": ("config.json", "pytorch_model.bin"),
    }

    def _type_of(self, repo: str) -> str:
        if mreg is None:
            return "mt"
        item = mreg.model_by_id(repo)
        return (item or {}).get("type", "mt")

    def verify_repo(self, repo: str) -> dict:
        """Проверить целостность установленной модели.

        HuggingFace при загрузке сам сверяет sha256 LFS-файлов; здесь
        дополнительно проверяем наличие обязательных файлов и размер
        относительно ожидаемого (защита от оборванной загрузки).
        """
        kind = self._type_of(repo)
        size = mreg.disk_size_mb(repo) if mreg else 0.0
        result = {"id": repo, "ok": False, "missing": [], "size_mb": size}
        if not mreg or not mreg.installed(repo):
            result["missing"] = ["модель не установлена"]
            return result
        base = os.path.join(mreg.hf_hub_dir(),
                            "models--" + repo.replace("/", "--"))
        names: set[str] = set()
        for root, _dirs, files in os.walk(base):
            names.update(files)
        missing = [f for f in self.REQUIRED_FILES.get(kind, ())
                   if not any(n == f or n.startswith(f) for n in names)]
        if missing:
            result["missing"] = missing
            return result
        expected = self._expected_mb(repo)
        if expected and size < expected * 0.85:
            result["missing"] = [f"файлы неполные ({size} из ~{expected} МБ)"]
            return result
        result["ok"] = True
        return result

    def _expected_mb(self, repo: str) -> float:
        if mreg is None:
            return 0.0
        if repo in mreg.ASR_SIZES_MB:
            return float(mreg.ASR_SIZES_MB[repo])
        item = mreg.model_by_id(repo)
        return float((item or {}).get("size_mb", 0) or 0)

    def _model_state(self, repo: str) -> str:
        if repo in getattr(self, "_download_ids", set()):
            return "DOWNLOADING"
        if not mreg or not mreg.installed(repo):
            return "NOT INSTALLED"
        kind = self._type_of(repo)
        if kind == "asr":
            return "READY" if repo == self.asr_model and self.asr \
                else "STOPPED"
        if kind == "tts":
            return "READY" if self.tts is not None else "STOPPED"
        # модель уже загружена в память, если она есть в любой цепочке
        for key in list(self._mt_cache):
            chain = self._mt_cache.get(key) or []
            if any(repo in getattr(self, "_chain_repos", {}).get(key, [])
                   for _ in chain):
                return "READY"
        return "STOPPED"

    def catalog(self) -> list[dict]:
        """Каталог моделей с фактическим состоянием установки."""
        if mreg is None:
            return []
        out = []
        for item in mreg.catalog():
            repo = item["repo"]
            row = {k: item[k] for k in
                   ("id", "type", "name", "repo", "developer", "source",
                    "description", "languages", "license", "size_mb",
                    "ram_mb", "vram_mb", "devices") if k in item}
            row["direction"] = item.get("direction", "")
            row["installed"] = bool(mreg.installed(repo))
            row["disk_mb"] = mreg.disk_size_mb(repo) if row["installed"] else 0
            row["state"] = self._model_state(repo)
            out.append(row)
        return out

    def _active_downloads(self) -> set:
        return getattr(self, "_download_ids", set())

    def cancel_download(self, request: str) -> None:
        self._cancel_requests.add(request or "")
        log(f"[engine] отмена загрузки {request!r}")

    def remove_model(self, repo: str) -> dict:
        """Удалить модель из кэша (если она не используется сейчас)."""
        if repo == self.asr_model and self.asr is not None:
            raise RuntimeError("модель распознавания используется — сначала "
                               "переключите или остановите движок")
        if not mreg or not mreg.installed(repo):
            return {"id": repo, "ok": True, "size_mb": 0}
        size = mreg.disk_size_mb(repo)
        base = os.path.join(mreg.hf_hub_dir(),
                            "models--" + repo.replace("/", "--"))
        # если модель в памяти — выгружаем её из кэша цепочек
        for key in list(self._mt_cache):
            self._mt_cache.pop(key, None)
        self.mt = None
        self.mt_tok = None
        shutil.rmtree(base, ignore_errors=True)
        log(f"[engine] модель удалена: {repo} ({size} МБ)")
        return {"id": repo, "ok": True, "size_mb": size}

    def download_repos(self, repos: list[str], request: str,
                       label: str = "") -> bool:
        """Скачать несколько моделей с прогрессом и отменой.

        Одна модели может входить в несколько пакетов — если она уже на
        диске, повторно не качается (используем существующий кэш).
        """
        request = request or ",".join(repos)
        for repo in repos:
            if mreg and mreg.installed(repo):
                emit({"event": "download", "request": request, "id": repo,
                      "state": "READY", "percent": 100, "label": label})
                continue
            if request in self._cancel_requests:
                self._cancel_requests.discard(request)
                emit({"event": "download", "request": request, "id": repo,
                      "state": "CANCELLED", "percent": 0,
                      "label": label})
                return False
            if not self._download_one(repo, request, label):
                return False
        return True

    def _download_one(self, repo: str, request: str, label: str) -> bool:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "download_model.py")
        expected = self._expected_mb(repo)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._download_ids = getattr(self, "_download_ids", set())
        self._download_ids.add(repo)
        emit({"event": "download", "request": request, "id": repo,
              "state": "DOWNLOADING", "percent": 0, "label": label,
              "expected_mb": expected})
        log(f"[engine] загрузка {repo} (~{expected} МБ)")
        try:
            proc = subprocess.Popen(
                [sys.executable, script, "--repo", repo],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=flags)
        except Exception as exc:  # noqa: BLE001
            self._download_ids.discard(repo)
            emit({"event": "download", "request": request, "id": repo,
                  "state": "ERROR", "label": label,
                  "message": f"{type(exc).__name__}: {exc}"})
            return False
        while proc.poll() is None:
            if request in self._cancel_requests:
                self._cancel_requests.discard(request)
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except Exception:
                    proc.kill()
                self._download_ids.discard(repo)
                log(f"[engine] загрузка {repo} отменена")
                emit({"event": "download", "request": request, "id": repo,
                      "state": "CANCELLED", "percent": 0, "label": label})
                return False
            cur = mreg.disk_size_mb(repo) if mreg else 0.0
            pct = int(min(99, cur * 100.0 / expected)) if expected else 0
            emit({"event": "download", "request": request, "id": repo,
                  "state": "DOWNLOADING", "percent": pct,
                  "mb": round(cur, 1), "expected_mb": expected,
                  "label": label})
            time.sleep(0.5)
        out, err = proc.communicate()
        self._download_ids.discard(repo)
        if proc.returncode != 0:
            msg = (err or out or "").strip().splitlines()
            msg = msg[-1] if msg else "неизвестная ошибка"
            log(f"[engine] {repo} не скачалась: {msg}")
            emit({"event": "download", "request": request, "id": repo,
                  "state": "ERROR", "percent": 0, "label": label,
                  "message": msg[:300]})
            return False
        emit({"event": "download", "request": request, "id": repo,
              "state": "INSTALLING", "percent": 100, "label": label})
        check = self.verify_repo(repo)
        if not check["ok"]:
            emit({"event": "download", "request": request, "id": repo,
                  "state": "ERROR", "label": label,
                  "message": "; ".join(check["missing"])[:300]})
            return False
        log(f"[engine] {repo} установлена ({check['size_mb']} МБ)")
        emit({"event": "download", "request": request, "id": repo,
              "state": "READY", "percent": 100, "label": label,
              "disk_mb": check["size_mb"]})
        return True

    def select_model(self, kind: str, model_id: str) -> dict:
        """Выбрать модель: asr / tts / mt (направление перевода)."""
        if kind == "asr":
            name = self.set_asr(model_id)
            self._bump_gen(f"выбор ASR {name}")
            return {"kind": "asr", "value": name}
        if kind == "tts":
            if model_id and model_id != "tts-hub/XTTS-v2":
                raise RuntimeError(f"неизвестная модель синтеза: {model_id}")
            return {"kind": "tts", "value": "tts-hub/XTTS-v2"}
        if kind == "mt":
            if mreg is None:
                raise RuntimeError("нет каталога моделей")
            item = mreg.model_by_id(model_id)
            if not item or item["type"] != "mt":
                raise RuntimeError(f"неизвестная модель перевода: {model_id}")
            src, dst = item["direction"].split("->")
            if src != "ru":
                raise RuntimeError("выбор языка перевода — это ru->X; "
                                   f"{src}->{dst} используется для входящей речи")
            code = self.set_lang(dst)
            self._bump_gen(f"выбор направления {src}->{dst}")
            return {"kind": "mt", "value": item["id"], "lang": code}
        raise RuntimeError(f"неизвестный тип модели: {kind}")

    # ---------- языковые пакеты ----------
    def packs(self) -> list[dict]:
        """Языковые пакеты: что есть, чего не хватает, сколько качать."""
        if mreg is None:
            return []
        out = []
        for pack in mreg.all_packs(self.src_lang):
            models = []
            missing = []
            missing_mb = 0
            for repo in pack["models"]:
                inst = bool(mreg.installed(repo))
                models.append({"id": repo, "installed": inst,
                               "size_mb": mreg.MT_REPO_SIZE_MB})
                if not inst:
                    missing.append(repo)
                    missing_mb += mreg.MT_REPO_SIZE_MB
            asr_ok = bool(mreg.installed(mreg.ASR_MODELS[0]["repo"]))
            tts_ok = bool(mreg.installed(mreg.TTS_MODELS[0]["repo"]))
            ready = (not missing and asr_ok and tts_ok
                     and pack["asr_supported"] and pack["tts_supported"])
            no_route = (pack["to_user"]["kind"] == "none"
                        or pack["from_user"]["kind"] == "none")
            if not pack["asr_supported"] or not pack["tts_supported"] \
                    or no_route:
                status = "UNSUPPORTED"
            elif ready:
                status = "READY"
            elif missing:
                status = "PARTIAL" if (asr_ok and tts_ok) else "NOT INSTALLED"
            else:
                status = "PARTIAL"
            out.append({**pack, "models": models, "missing": missing,
                        "missing_mb": missing_mb, "asr_installed": asr_ok,
                        "tts_installed": tts_ok, "status": status})
        return out

    def pack_install(self, code: str, request: str = "") -> bool:
        pack = next((p for p in self.packs() if p["code"] == code), None)
        if pack is None:
            raise RuntimeError(f"нет языкового пакета: {code}")
        if not pack["asr_supported"] or not pack["tts_supported"]:
            raise RuntimeError(f"язык {code} не поддержан ASR/TTS")
        missing = [m["id"] for m in pack["models"] if not m["installed"]]
        if not missing:
            emit({"event": "pack", "code": code, "state": "READY",
                  "percent": 100})
            return True
        emit({"event": "pack", "code": code, "state": "DOWNLOADING",
              "percent": 0, "models": missing,
              "size_mb": pack["missing_mb"]})
        ok = self.download_repos(missing, request or f"pack:{code}",
                                label=f"пакет {code}")
        state = "READY" if ok else "ERROR"
        emit({"event": "pack", "code": code, "state": state,
              "percent": 100 if ok else 0})
        return ok

    def pack_remove(self, code: str) -> dict:
        pack = next((p for p in self.packs() if p["code"] == code), None)
        if pack is None:
            raise RuntimeError(f"нет языкового пакета: {code}")
        # общие модели других пакетов не трогаем
        others: set[str] = set()
        for other in self.packs():
            if other["code"] != code:
                others.update(m["id"] for m in other["models"])
        removed = []
        freed = 0.0
        for m in pack["models"]:
            if not m["installed"] or m["id"] in others:
                continue
            res = self.remove_model(m["id"])
            removed.append(m["id"])
            freed += float(res.get("size_mb", 0) or 0)
        emit({"event": "pack", "code": code, "state": "REMOVED",
              "percent": 0, "removed": removed, "freed_mb": round(freed, 1)})
        return {"removed": removed, "freed_mb": round(freed, 1)}

    def download_package(self, src: str) -> bool:
        """Скачать всё, что нужно для перевода src->ru (автозагрузка)."""
        if mreg is None:
            return False
        repos = mreg.route(src, "ru") or []
        if not repos:
            return False
        pair = f"{src}->ru"
        emit({"event": "package", "pair": pair, "state": "downloading",
              "models": repos})
        log(f"[engine] загрузка пакета {pair}: {repos}")
        ok = self.download_repos(repos, f"auto:{pair}", label=pair)
        self._downloaded.add(pair)
        emit({"event": "package", "pair": pair,
              "state": "installed" if ok else "error"})
        return ok

    def reverse_available(self, src: str) -> bool:
        """Есть ли чем перевести чужую речь на русский (модели на диске)."""
        if src in ("", "auto", "ru"):
            return True
        if mreg is None:
            chain = _reverse_mt_names(src)
            return bool(chain) and all(_model_installed(_chain_name(i))
                                       for i in chain)
        repos = mreg.route(src, "ru")
        if not repos:
            return False
        return all(mreg.installed(r) for r in repos)

    # ---------- языки ----------
    def set_lang(self, code: str) -> str:
        """Переключить язык перевода. Возвращает код (или прежний при сбое).

        Модель перевода для нового языка грузится при первом переключении
        (несколько секунд) — дальше она в кэше.
        """
        code = (code or "").lower().strip()
        if code == self.lang:
            return self.lang
        info = _lang_info(code)
        # Список допустимых языков — из voice_lang (es/en/ow/it/mg).
        # Раньше он был жёстко зашит из 4 языков, и мегрельский отбрасывался
        # молча: перевод шёл на ПРЕДЫДУЩИЙ язык.
        allowed = ("es", "en", "ow", "it")
        if voice_lang is not None:
            try:
                allowed = tuple(voice_lang.LANG_ORDER)
            except Exception:
                pass
        if code not in allowed:
            log(f"[engine] неизвестный язык: {code!r}")
            return self.lang
        # Освобождаем память ДО загрузки: мегрельская цепочка (opus-mt-en-mul
        # ~800 МБ) часто не влезает рядом с уже загруженной итальянской.
        # Без этого процесс падал по OOM без сообщения («тихий краш»).
        # Ключ кэша — 'chain:<язык>', а не просто код: раньше условие
        # сравнивало код с ключами и всегда было истинным, поэтому кэш
        # сбрасывался при каждом переключении (2-18 с к первой фразе).
        # Теперь чистим только когда модели реально не помещаются.
        chain_key = f"chain:{code}"
        loaded_chains = [k for k in self._mt_cache if k.startswith("chain:")]
        if chain_key not in self._mt_cache and len(loaded_chains) >= MT_CACHE_CHAINS:
            log(f"[engine] смена языка {self.lang} -> {code}: "
                f"освобождаю кэш MT (RSS={_rss_mb():.0f} МБ)")
            self._clear_mt_cache(keep=code)
            try:
                import gc
                gc.collect()
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        try:
            self._mt_for(code)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] не удалось загрузить перевод для {code}: "
                f"{type(exc).__name__}: {exc}")
            return self.lang
        self.lang = code
        self._bump_gen(f"язык перевода {code}")
        log(f"[engine] язык перевода: {code} ({info['title']}), "
            f"XTTS: {info['xtts']}, RSS={_rss_mb():.0f} МБ")
        return self.lang

    def unload_models(self) -> None:
        """Выгрузить все модели из памяти, не завершая процесс.

        Нужно, чтобы после «Остановить модель» RAM реально освобождалась.
        Раньше процесс просто убивался, и Windows держала 5+ ГБ.
        """
        import gc
        log(f"[engine] выгрузка моделей (RSS={_rss_mb():.0f} МБ)")
        # Очереди — чтобы не держать ссылки на аудио
        try:
            self._clear_mt_cache()
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] очистка MT: {exc}")
        for name in ("asr", "tts", "mt", "mt_tok"):
            try:
                setattr(self, name, None)
            except Exception:
                pass
        for name in ("gpt_latent", "spk_emb"):
            try:
                setattr(self, name, None)
            except Exception:
                pass
        try:
            self._peer_q = queue.Queue(maxsize=8)
        except Exception:
            pass
        try:
            self.last_spoken.clear()
        except Exception:
            pass
        for _ in range(3):
            gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
        self.loaded = False
        self._chain_repos.clear()
        log(f"[engine] модели выгружены (RSS={_rss_mb():.0f} МБ)")

    def _clear_mt_cache(self, keep: str = "") -> None:
        """Освободить загруженные модели перевода (кроме ключей для `keep`)."""
        for k in list(self._mt_cache):
            if keep and (k == f"chain:{keep}" or k == f"rev:{keep}"):
                continue
            old = self._mt_cache.pop(k, None)
            log(f"[engine] модель перевода {k} выгружена из памяти")
            del old
        self.mt_tok = None
        self.mt = None

    def _queue_len(self) -> list:
        """Размер внутренних очередей (для метрик)."""
        return [self._peer_q.qsize()]

    def _mt_for(self, code: str) -> list[tuple]:
        """Модели перевода ru -> язык (грузятся при первом обращении).

        Возвращает список пар (токенизатор, модель) — это цепочка: для
        итальянского это ru->es->it (прямой модели ru->it не существует).
        """
        return self._load_chain(f"chain:{code}", _mt_names(code))

    def _mt_reverse(self, src: str, dst: str = "ru") -> list[tuple]:
        """Модели перевода язык -> язык пользователя (для чужих игроков).

        Маршрут берётся из реестра: прямая пара, а если её нет — через
        английский. Раньше английский подставлялся как замена перевода —
        теперь это только язык-посредник.
        """
        if mreg is None:
            names = _reverse_mt_names(src)
        else:
            names = mreg.route(src, dst) or []
        if not names:
            return []
        return self._load_chain(f"rev:{src}:{dst}", names)

    def _load_chain(self, key: str, names: list) -> list[tuple]:
        """Загрузить (и закэшировать) цепочку моделей перевода.

        Элемент names — строка (имя модели) либо кортеж (имя, target-токен).
        Target-токен нужен для мультиязычных моделей (opus-mt-en-mul):
        >>kat<< = грузинский, >>spa<< = испанский и т.д.
        """
        if key in self._mt_cache:
            return self._mt_cache[key]
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        t0 = time.time()
        chain = []
        plain_names = []
        for item in names:
            if isinstance(item, (list, tuple)):
                name = item[0]
                target = item[1] if len(item) > 1 else None
            else:
                name = item
                target = None
            plain_names.append(name)
            tok = AutoTokenizer.from_pretrained(name)
            # float16 и на CPU: вдвое меньше RAM (критично для цепочек
            # вроде ru->en->ka, где две модели ~600 МБ в float32).
            dtype = torch.float16
            try:
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    name, dtype=dtype, low_cpu_mem_usage=True).to(self.mt_device).eval()
            except Exception:
                # не все CPU поддерживают fp16-матмулы — откатываемся
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    name, dtype=torch.float32,
                    low_cpu_mem_usage=True).to(self.mt_device).eval()
            if target:
                chain.append((tok, model, target))
            else:
                chain.append((tok, model))
        # Кэш: не больше двух языков (текущий + испанский) — RAM конечен.
        # Считаем только прямые цепочки: обратные (rev:) не вытесняются.
        direct = [k for k in self._mt_cache if k.startswith("chain:")]
        if len(direct) >= MT_CACHE_CHAINS and key not in self._mt_cache:
            keep = {key}
            if "chain:es" in self._mt_cache and key != "chain:es":
                keep.add("chain:es")
            for k in list(self._mt_cache):
                if k not in keep:
                    old = self._mt_cache.pop(k)
                    log(f"[engine] модель перевода {k} выгружена из памяти")
                    del old
                    try:
                        import gc
                        gc.collect()
                    except Exception:
                        pass
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
        self._mt_cache[key] = chain
        self._chain_repos[key] = plain_names
        self.mt_tok, self.mt = chain[0][0], chain[0][1]
        log(f"[engine] модель перевода {' -> '.join(plain_names)} загружена за "
            f"{int((time.time() - t0) * 1000)} мс, "
            f"RSS={_rss_mb():.0f} МБ, кэш={list(self._mt_cache)}")
        return chain


    def _load_tts(self, reference: str) -> None:
        import glob
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        hf = os.path.expanduser(r"~\.cache\huggingface\hub")
        snaps = glob.glob(os.path.join(hf, "models--tts-hub--XTTS-v2", "snapshots", "*"))
        if not snaps:
            raise RuntimeError(
                f"нет модели XTTS-v2 в кэше HuggingFace ({hf}). "
                f"Проверь, что движок установлен и модель скачана.")
        snap = snaps[0]
        log(f"[engine] XTTS: {snap}")

        # torchaudio -> soundfile (обход torchcodec/FFmpeg)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            import xtts_clone
            xtts_clone.patch_torchaudio()
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] не удалось применить патч torchaudio: {exc}")

        t0 = time.time()
        cfg = XttsConfig()
        cfg.load_json(os.path.join(snap, "config.json"))
        self.tts = Xtts.init_from_config(cfg)
        self.tts.load_checkpoint(cfg, checkpoint_dir=snap,
                                 vocab_path=os.path.join(snap, "vocab.json"))
        self.tts.cuda()
        try:
            import torch
            log(f"[engine] VRAM XTTS: allocated "
                f"{torch.cuda.memory_allocated() / 2**20:.0f} МБ, "
                f"reserved {torch.cuda.memory_reserved() / 2**20:.0f} МБ")
        except Exception:
            pass
        # кэш голоса: считается один раз (1.4 с), дальше 0.03 с
        self.gpt_latent, self.spk_emb = self.tts.get_conditioning_latents(
            audio_path=[reference])
        self._reference_sig = _ref_sig(reference)
        log(f"[engine] XTTS + кэш голоса за {(time.time() - t0) * 1000:.0f} мс, "
            f"RSS={_rss_mb():.0f} МБ")
        self._warmup_tts()

    def _warmup_tts(self) -> None:
        """Прогреть XTTS одним выброшенным синтезом.

        Замер (build/quality_sweep.py): первый синтез после загрузки
        выдавал неразборчивую фразу (WER 0.86), последующие — 0.14–0.2,
        и первый чанк ждал 5 с вместо ~1 с. Прогрев платит за это время
        на загрузке, а не в живом разговоре.
        """
        t0 = time.time()
        try:
            lang = xtts_language(self.lang) if self.lang else "es"
            for _chunk in self.tts.inference_stream(
                    "Hola, ¿qué tal?", lang, self.gpt_latent, self.spk_emb,
                    stream_chunk_size=self.stream_chunk,
                    overlap_wav_len=2048,
                    temperature=0.75, top_p=0.86, top_k=50,
                    speed=1.0, repetition_penalty=10.0):
                break   # достаточно первого чанка
            log(f"[engine] XTTS прогрет за {(time.time() - t0) * 1000:.0f} мс")
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] прогрев XTTS не удался: {type(exc).__name__}: {exc}")

    def set_reference(self, reference: str) -> bool:
        """Сменить тембр голоса без перезагрузки ASR/MT/XTTS."""
        reference = (reference or "").strip()
        if not reference or not os.path.exists(reference):
            log(f"[engine] reference не найден: {reference}")
            return False
        if self.tts is None:
            self.reference = reference
            self._reference_sig = _ref_sig(reference)
            return True
        sig = _ref_sig(reference)
        if sig == getattr(self, "_reference_sig", ("", 0, 0)) \
                and self.spk_emb is not None and sig[0]:
            return True
        t0 = time.time()
        try:
            with self.lock:
                gpt, spk = self.tts.get_conditioning_latents(
                    audio_path=[reference])
                self.gpt_latent, self.spk_emb = gpt, spk
                self.reference = reference
                self._reference_sig = sig
            log(f"[engine] голос пересобран за {(time.time() - t0) * 1000:.0f} мс: "
                f"{reference}")
            return True
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] не удалось переключить голос: "
                f"{type(exc).__name__}: {exc}")
            return False

    # ---------- перевод текста ----------
    def _ensure_state(self) -> None:
        """Доставить поля кэша/глоссария, если объект создан без __init__.

        Нужно тестам и любым внешним сборкам Engine.__new__(...).
        """
        if not hasattr(self, "_text_cache"):
            self._text_cache = OrderedDict()
        if not hasattr(self, "_text_cache_lock"):
            self._text_cache_lock = threading.Lock()
        if not hasattr(self, "_text_cache_max"):
            self._text_cache_max = 512
        if not hasattr(self, "cache_hits"):
            self.cache_hits = 0
        if not hasattr(self, "cache_misses"):
            self.cache_misses = 0
        if not hasattr(self, "glossary"):
            self.glossary = None

    def _glossary(self):
        """Глоссарий: один раз читаем файл, дальше держим в памяти."""
        self._ensure_state()
        if self.glossary is None:
            if glos is None:
                self.glossary = False
            else:
                try:
                    glos.ensure_file()
                    self.glossary = glos.Glossary.load()
                    log(f"[engine] глоссарий: терминов {len(self.glossary.entries)}")
                except Exception as exc:  # noqa: BLE001
                    log(f"[engine] глоссарий не загружен: {exc}")
                    self.glossary = False
        return self.glossary or None

    def _cache_get(self, key: tuple) -> str | None:
        self._ensure_state()
        with self._text_cache_lock:
            val = self._text_cache.get(key)
            if val is None:
                self.cache_misses += 1
                return None
            self._text_cache.move_to_end(key)
            self.cache_hits += 1
            return val

    def _cache_put(self, key: tuple, value: str) -> None:
        if not value:
            return
        self._ensure_state()
        with self._text_cache_lock:
            self._text_cache[key] = value
            self._text_cache.move_to_end(key)
            while len(self._text_cache) > self._text_cache_max:
                self._text_cache.popitem(last=False)

    def _run_chain(self, text: str, chain: list[tuple], beam: int = 1,
                   dst: str = "", use_glossary: bool = True) -> str:
        """Прогнать текст по цепочке моделей перевода.

        Элемент цепочки — пара (токенизатор, модель) либо
        (токенизатор, модель, target_токен). Target-токен нужен для
        мультиязычных моделей (opus-mt-en-mul): >>kat<< = грузинский.
        """
        import torch
        # Имена и термины прячем за метками, чтобы модель их не переводила
        used: list[dict] = []
        g = self._glossary() if use_glossary else None
        if g is not None:
            text, used = g.protect(text)
        for item in chain:
            tok, model = item[0], item[1]
            target = item[2] if len(item) > 2 else None
            batch = tok([text], return_tensors="pt", padding=True).to(
                getattr(model, "device", MT_DEVICE))
            gen_kwargs = {}
            if target:
                try:
                    tid = tok.convert_tokens_to_ids(target)
                    if tid is not None and tid != tok.unk_token_id:
                        gen_kwargs["forced_bos_token_id"] = tid
                except Exception:
                    pass
            with torch.inference_mode():
                # Лимит длины — от длины входа: 128 токенов хватало только
                # на короткую реплику, а склеенная (одна фраза из нескольких
                # кусков) обрезалась на середине — терялся её конец.
                max_tokens = max(128, min(512, 4 * len(text.split()) + 32))
                out = model.generate(**batch, max_new_tokens=max_tokens,
                                     num_beams=max(1, int(beam)),
                                     **gen_kwargs)
            text = tok.batch_decode(out, skip_special_tokens=True)[0].strip()
            # Мультиязычная модель оставляет префикс цели — убираем
            if target and text.startswith(target.strip(">")):
                text = text.split(None, 1)[1] if " " in text else ""
        if used:
            text = g.restore(text, used, dst)
        return text

    def translate_text(self, ru: str) -> str:
        if not ru.strip():
            return ""
        key = ("out", self.lang, ru.strip())
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        chain = self._mt_for(self.lang)
        text = self._run_chain(ru, chain, beam=MT_BEAMS_FORWARD, dst=self.lang)
        # Олдвест: это английский, переписанный словами ковбойской речи.
        # Лишней модели и задержки это не добавляет.
        if self.lang == "ow" and voice_lang is not None:
            text = voice_lang.to_oldwest(text)
        self._cache_put(key, text)
        if MT_LOG_TEXT:
            log(f"[mt] ru->{self.lang}: {ru.strip()!r} -> {text!r}")
        return text

    def translate_to_ru(self, text: str, src: str) -> str:
        """Перевести чужую речь на русский (перехват игроков).

        Если для языка есть прямая модель (es/en/it) — используем её.
        Иначе — запасной путь через английский (см. _translate_via_english),
        который требует исходного аудио: Whisper сам переводит речь
        на английский (task="translate"), дальше eng->ru одной моделью.
        """
        if not text.strip() or src in ("", "auto", "ru"):
            return text
        key = ("rev", src, text.strip())
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        chain = self._mt_reverse(src)
        if not chain:
            return ""
        try:
            # Глоссарий здесь НЕ применяется. Он подставляет русский термин
            # как есть, а opus-mt ставит вокруг метки нужный падеж — в итоге
            # получалось «увидел Артур Морган» и «сексом с осёл» вместо
            # «с ослом». Замер (es->ru, beam 4): с защитой — «увидел Марса,
            # занимавшегося сексом с осёл», без неё — «…с ослом»;
            # «увидел Артур Морган» -> «увидел Артура Моргана».
            out = self._run_chain(text, chain, beam=MT_BEAMS_REVERSE,
                                  dst="ru", use_glossary=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] перевод {src}->ru не удался: "
                f"{type(exc).__name__}: {exc}")
            return ""
        self._cache_put(key, out)
        if MT_LOG_TEXT:
            log(f"[mt] {src}->ru: {text.strip()!r} -> {out!r}")
        return out

    def _translate_peer_to_ru(self, text: str, src: str,
                              pcm_bytes: bytes, sr: int) -> str:
        """Полный перевод чужой речи на русский (с запасным путём).

        Возвращает перевод или исходный текст, если перевести не удалось.
        """
        if not text.strip():
            return text
        if src == "ru":
            return text
        ru = self.translate_to_ru(text, src)
        if ru:
            return ru
        if mreg is not None and (mreg.route(src, "ru") or []):
            # маршрут есть, но модели не установлены — английским не подменяем
            return ""
        # Прямой модели нет — переводим аудио на английский через Whisper
        en = self._transcribe_as_english(pcm_bytes, sr)
        if not en:
            log(f"[engine] перевод {src}->ru: нет модели и не удалось "
                f"перевести на английский")
            return text
        chain = self._load_chain("rev:en", _reverse_mt_names("en"))
        if not chain:
            return en
        try:
            return self._run_chain(en, chain, beam=MT_BEAMS_REVERSE,
                                   dst="ru", use_glossary=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] en->ru не удался: {exc}")
            return en

    def _transcribe_as_english(self, pcm_bytes: bytes, sr: int) -> str:
        """Распознать речь с переводом на английский (Whisper task=translate)."""
        import numpy as np
        try:
            audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(
                np.float32) / 32768.0
            if sr != SR_ASR:
                from math import gcd
                from scipy.signal import resample_poly
                g = gcd(int(sr), SR_ASR)
                audio = resample_poly(
                    audio, SR_ASR // g, int(sr) // g).astype(np.float32)
            peak = float(np.abs(audio).max()) if audio.size else 0.0
            if peak > 1e-4:
                audio = audio / peak * 0.7
            segs, _ = self.asr.transcribe(
                audio, task="translate", beam_size=self.beam_size,
                vad_filter=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.6, log_prob_threshold=-1.0)
            items = list(segs)
            if not items:
                return ""
            speech = [s for s in items
                      if getattr(s, "no_speech_prob", 0.0) < 0.6
                      and getattr(s, "avg_logprob", -1.0) > -1.2]
            if not speech:
                return ""
            text = " ".join(s.text.strip() for s in speech).strip()
            if not text or is_hallucination(text):
                return ""
            return text
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] перевод на английский не удался: "
                f"{type(exc).__name__}: {exc}")
            return ""

    # ---------- распознавание ----------
    def transcribe(self, pcm_bytes: bytes, sr: int = SR_ASR,
                   floor: float = 0.0) -> str:
        """Распознать русскую речь. На входе — int16 моно с частотой sr.

        floor — уровень шума комнаты (если передан): фрагмент тише этого
        уровня — это шум, а не речь. Без такой проверки Whisper на шуме
        выдаёт «Субтитры сделал DimaTorzok» — и это озвучивается.
        """
        import numpy as np
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if sr != SR_ASR:
            # scipy есть только в движке (в EXE исключён) — ресемплим здесь
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(sr), SR_ASR)
            audio = resample_poly(audio, SR_ASR // g, int(sr) // g).astype(np.float32)

        # Проверка уровня: решает СТРУКТУРА внутри фрагмента, а не абсолютный
        # floor. Раньше `seg_rms < floor*2.2` выбрасывал тихую речь целиком,
        # хотя пиковая нормализация ниже всё равно приводит её к одному
        # уровню с громкой. Шумовой пол — 20-й процентиль кадров, громкое —
        # 90-й: у шума они почти равны, у речи расходятся в 3…10 раз.
        if audio.size:
            win = int(SR_ASR * 0.02)
            n = audio.size // win
            if n >= 4:
                fr = audio[:n * win].reshape(n, win).astype(np.float64)
                fr = np.sqrt(np.mean(np.square(fr), axis=1))
                quiet = float(np.percentile(fr, 20))
                loud = float(np.percentile(fr, 90))
                if loud <= max(quiet * 2.0, 1e-7):
                    log(f"[engine] речи во фрагменте нет (тихо {quiet:.5f}, "
                        f"громко {loud:.5f}, floor {floor:.5f}) — пропускаю")
                    return ""

        # Микрофон тихий (RMS ~0.01), а Whisper ждёт нормальный уровень:
        # на тихом звуке он часто НИЧЕГО не узнаёт. Нормализуем.
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 1e-4:
            audio = audio / peak * 0.7

        # Что именно получил Whisper: строка в live_engine_stderr.log.
        # Без неё нельзя отличить «тихо записалось» от «тихо распозналось».
        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
        log(f"[asr] {audio.size / SR_ASR:.2f}с rms={20.0 * np.log10(max(rms, 1e-9)):.1f}дБ "
            f"пик={20.0 * np.log10(max(peak, 1e-9)):.1f}дБ floor={floor:.5f}")

        # no_speech_threshold/log_prob_threshold — отсекаем пустые сегменты
        segs, _ = self.asr.transcribe(
            audio, language=self.src_lang, beam_size=self.beam_size,
            vad_filter=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6, log_prob_threshold=-1.0)
        # faster-whisper отдаёт генератор — собираем ОДИН раз
        items = list(segs)
        if not items:
            return ""
        # отсекаем сегменты, которые Whisper считает «не речью»
        speech = [s for s in items
                  if getattr(s, "no_speech_prob", 0.0) < 0.6
                  and getattr(s, "avg_logprob", -1.0) > -1.2]
        if not speech:
            return ""
        text = " ".join(s.text.strip() for s in speech).strip()
        if is_hallucination(text):
            log(f"[engine] отброшено как галлюцинация: {text!r}")
            return ""
        return text

    # ---------- перехват речи других игроков ----------
    def set_peer_lang(self, code: str) -> str:
        """Язык чужой речи: auto (определяем) или конкретный код."""
        code = (code or "auto").lower().strip()
        allowed = ("auto",)
        if voice_lang is not None:
            allowed = tuple(getattr(voice_lang, "PEER_LANG_CODES", allowed))
        if code not in allowed:
            code = "auto"
        self.peer_lang = code
        self._reset_peer_parts("смена языка собеседника")
        self._bump_gen(f"язык собеседника {code}")
        self._lang_hits.clear()
        if code != "auto":
            # ручной выбор сразу становится подтверждённым и не
            # перезаписывается автоматикой
            self.peer_lang_confirmed = code
        log(f"[engine] язык чужой речи: {self.peer_lang}")
        emit({"event": "peer_lang", "code": self.peer_lang,
              "auto": code == "auto", "prob": 0.0,
              "confirmed": self.peer_lang_confirmed})
        return self.peer_lang

    def push_peer_pcm(self, pcm_bytes: bytes, sr: int = SR_ASR,
                      partial: bool = False, last: bool = True,
                      phrase: int | None = None) -> bool:
        """Отдать фрагмент звука игры на разбор (что говорят игроки).

        partial=True — промежуточный срез ещё не законченной реплики:
        он только показывается в интерфейсе и НЕ переводится.
        last=False — кусок одной фразы: движок скопит куски и обработает
        фразу целиком (иначе длинная реплика рвётся на куски по 5 с).
        phrase — номер фразы: куски с другим номером не склеиваются с
        остатком предыдущей (если её последний кусок потерялся).
        """
        if not pcm_bytes:
            return False
        item = (pcm_bytes, sr, bool(partial), bool(last),
                None if phrase is None else int(phrase), time.time())
        try:
            self._peer_q.put_nowait(item)
        except queue.Full:
            # Очередь ограничена: лучше потерять промежуточный срез, чем
            # копить задержку. Финальные фрагменты важнее — при перегрузке
            # отбрасываем самый старый промежуточный.
            if partial:
                self.dropped += 1
                return False
            try:
                old = self._peer_q.get_nowait()
                self.dropped += 1
                if not (len(old) > 2 and old[2]):
                    # выкинули финальный фрагмент — вернём его в очередь
                    self._peer_q.put_nowait(old)
                    self.dropped += 1
                    return False
                # выкинули промежуточный срез; недосклеенные куски фразы
                # после дырки не имеют смысла
                self._reset_peer_parts("потерян кусок в очереди")
                self._peer_q.put_nowait(item)
            except (queue.Empty, queue.Full):
                self.dropped += 1
                return False
        return True

    def _reset_peer_parts(self, reason: str = "") -> None:
        """Выбросить недосклеенный остаток фразы (не приклеивать к новой)."""
        if self._peer_parts:
            log(f"[engine] остаток реплики собеседника отброшен "
                f"({len(self._peer_parts)} куск., {reason})")
        self._peer_parts = []
        self._peer_parts_id = None
        self._peer_parts_at = 0.0

    def _peer_parts_stale(self, phrase: int | None, now: float) -> bool:
        """Остаток относится к другой/слишком старой фразе."""
        if not self._peer_parts:
            return False
        if phrase is not None and self._peer_parts_id is not None \
                and phrase != self._peer_parts_id:
            return True
        return (now - self._peer_parts_at) >= PEER_PARTS_TTL

    def _join_peer_parts(self, pcm: bytes, last: bool,
                         phrase: int | None = None) -> bytes | None:
        """Склеить куски одной фразы. None — фраза ещё не закончилась."""
        now = time.time()
        if self._peer_parts_stale(phrase, now):
            self._reset_peer_parts(
                f"фраза {phrase}, в буфере {self._peer_parts_id}, "
                f"возраст {now - self._peer_parts_at:.1f} с")
        if not last:
            if not self._peer_parts:
                self._peer_parts_at = now
            self._peer_parts.append(pcm)
            if phrase is not None:
                self._peer_parts_id = phrase
            if sum(len(p) for p in self._peer_parts) > PEER_PARTS_MAX_BYTES:
                self._reset_peer_parts("переполнение буфера кусков")
            return None
        if self._peer_parts:
            pcm = b"".join(self._peer_parts + [pcm])
        self._peer_parts = []
        self._peer_parts_id = None
        self._peer_parts_at = 0.0
        return pcm

    def _peer_loop(self) -> None:
        """Поток разбора чужой речи: звук -> текст -> перевод на русский."""
        while True:
            try:
                item = self._peer_q.get(timeout=0.5)
            except queue.Empty:
                continue
            pcm, sr = item[0], item[1]
            partial = bool(item[2]) if len(item) > 2 else False
            last = bool(item[3]) if len(item) > 3 else True
            phrase = item[4] if len(item) > 4 else None
            arrival = float(item[5]) if len(item) > 5 else time.time()
            if not partial:
                joined = self._join_peer_parts(pcm, last, phrase)
                if joined is None:
                    continue
                pcm = joined
            gen = self.gen
            t0 = time.time()
            try:
                text, lang = self.transcribe_peer(pcm, sr, partial=partial)
                asr_ms = int((time.time() - t0) * 1000)
                if gen != self.gen:
                    self.cancelled += 1
                    log("[engine] результат устарел (смена режима/языка/"
                        "модели) — отброшен")
                    continue
                if not text:
                    if not partial:
                        self._peer_skip(self._asr_skip or "empty",
                                        f"{len(pcm) / (2 * max(1, sr)):.1f} с")
                    continue
                if partial:
                    # Промежуточный текст: только для показа, без перевода.
                    self._peer_seq += 1
                    emit({"event": "peer_partial", "text": text,
                          "lang": lang or self.peer_lang_confirmed,
                          "seq": self._peer_seq, "asr_ms": asr_ms})
                    continue
                if self._is_own_voice(text):
                    self._peer_skip("own_voice", text[:40])
                    log(f"[engine] перехват: это наш собственный голос, "
                        f"пропускаю ({text!r})")
                    continue
                key = " ".join(text.lower().split())
                if key and key == self._last_translated:
                    self.cancelled += 1
                    self._peer_skip("duplicate", key[:40])
                    log("[engine] та же фраза уже переведена — пропускаю")
                    continue
                self._last_translated = key
                if not self.reverse_available(lang):
                    # Если пользователь разрешил автоскачивание — скачиваем
                    # пакет и продолжаем с ЭТОЙ ЖЕ фразой (не теряем её).
                    if self.auto_download and self.download_package(lang):
                        log(f"[engine] пакет {lang}->ru готов, продолжаю фразу")
                    else:
                        self._peer_skip("no_mt", f"{lang}->ru")
                        # Не подменяем перевод английским текстом: лучше явно
                        # сказать, что для направления нет модели.
                        log(f"[engine] перехват {lang}->ru: нет модели перевода")
                        emit({"event": "peer_text", "src": text, "ru": "",
                              "lang": lang, "missing_mt": f"{lang}->ru",
                              "can_download": not self.auto_download})
                        continue
                t_mt = time.time()
                ru = self._translate_peer_to_ru(text, lang, pcm, sr)
                mt_ms = int((time.time() - t_mt) * 1000)
                if gen != self.gen:
                    self.cancelled += 1
                    log("[engine] перевод устарел — отброшен")
                    continue
                if not (ru or "").strip():
                    self._peer_skip("empty_ru", f"{lang}: {text[:40]}")
                # Озвучку закажет GUI; к этому моменту известны ASR/MT —
                # сохраняем их, чтобы строка «фраза целиком» содержала все этапы.
                self._pending_timings.append({
                    "ru": ru, "lang": lang,
                    "arrival": arrival,
                    "wait_ms": max(0, int((t0 - arrival) * 1000)),
                    "asr_ms": asr_ms, "mt_ms": mt_ms,
                })
                if len(self._pending_timings) > 8:
                    self._pending_timings.pop(0)
                emit({"event": "peer_text", "src": text, "ru": ru,
                      "lang": lang, "asr_ms": asr_ms, "mt_ms": mt_ms,
                      "total_ms": int((time.time() - t0) * 1000),
                      "queue": self._peer_q.qsize(),
                      "dropped": self.dropped,
                      "cancelled": self.cancelled})
            except Exception as exc:  # noqa: BLE001
                log(f"[engine] перехват не удался: {type(exc).__name__}: {exc}")

    def _is_own_voice(self, text: str) -> bool:
        """Похоже ли это на нашу собственную озвучку?

        Перевод идёт и в наушники, поэтому запись игры может поймать его.
        Отсекаем по совпадению текста.
        """
        import difflib
        import re

        def norm(t: str) -> str:
            t = re.sub(r"[¿?¡!.,;:]", " ", (t or "").lower())
            return " ".join(t.split())

        heard = norm(text)
        if not heard:
            return True
        now = time.time()
        for own in self.last_spoken:
            # Память об эхе короткая: своя озвучка возвращается через
            # наушники в игру за секунды. Без ограничения по времени
            # повтор собеседником той же фразы ошибочно считался своим
            # голосом и терялся.
            if isinstance(own, tuple):
                own_text, own_ts = own
            else:
                own_text, own_ts = own, now
            if now - own_ts > 8.0:
                continue
            if difflib.SequenceMatcher(None, norm(own_text),
                                       heard).ratio() >= 0.55:
                return True
        return False

    def transcribe_peer(self, pcm_bytes: bytes, sr: int = SR_ASR,
                        partial: bool = False) -> tuple[str, str]:
        """Распознать чужую речь. Возвращает (текст, язык).

        partial=True — промежуточное декодирование растущего фрагмента:
        быстрый beam=1, без определения языка и без порогов финализации.
        Это НЕ потоковое декодирование Whisper, а инкрементальные срезы:
        окончательный текст даёт финальный фрагмент после VAD-паузы.
        """
        import numpy as np
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if sr != SR_ASR:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(sr), SR_ASR)
            audio = resample_poly(
                audio, SR_ASR // g, int(sr) // g).astype(np.float32)
        # Та же проверка, что и для своей речи: тишина/ровный шум — не речь.
        # Без неё пиковая нормализация ниже делает из шума «речь», и Whisper
        # на нём сочиняет целые фразы (в живом тесте так появился перевод
        # «Значит, я пойду к тебе…», которого никто не говорил).
        if audio.size:
            win = int(SR_ASR * 0.02)
            n = audio.size // win
            if n >= 4:
                fr = audio[:n * win].reshape(n, win).astype(np.float64)
                fr = np.sqrt(np.mean(np.square(fr), axis=1))
                quiet = float(np.percentile(fr, 20))
                loud = float(np.percentile(fr, 90))
                if loud <= max(quiet * 2.0, 1e-7):
                    self._asr_skip = "no_speech"
                    return "", self.peer_lang
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 1e-4:
            audio = audio / peak * 0.7
        self._asr_skip = ""
        lang = None if self.peer_lang == "auto" else self.peer_lang
        segs, info = self.asr.transcribe(
            audio, language=lang,
            beam_size=1 if partial else self.beam_size, vad_filter=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6, log_prob_threshold=-1.0)
        items = list(segs)
        if not items:
            self._asr_skip = "no_speech"
            return "", self.peer_lang
        speech = [s for s in items
                  if getattr(s, "no_speech_prob", 0.0) < 0.6
                  and getattr(s, "avg_logprob", -1.0) > -1.2]
        if not speech:
            self._asr_skip = "no_speech"
            return "", self.peer_lang
        text = " ".join(s.text.strip() for s in speech).strip()
        # Известные ослышки имён: «Mars al»/«Marsal» — это «Marshall».
        text = fix_asr_names(text)
        if not text:
            self._asr_skip = "empty"
            return "", self.peer_lang
        if is_hallucination(text):
            self._asr_skip = "hallucination"
            return "", self.peer_lang
        if partial:
            return text, self.peer_lang_confirmed or (
                "" if self.peer_lang == "auto" else self.peer_lang)
        dur = audio.size / float(SR_ASR)
        words = len(text.split())
        detected = (getattr(info, "language", None) or "").lower()
        prob = float(getattr(info, "language_probability", 0.0) or 0.0)
        if self.peer_lang != "auto":
            # Ручной выбор всегда приоритетнее автоматики.
            self.peer_lang_confirmed = self.peer_lang
            return text, self.peer_lang
        if detected == "ru" and _cyrillic_share(text) < 0.5:
            # «Русский» без единой кириллической буквы — это ошибка
            # определения: текст испанца уходил в озвучку без перевода.
            # До подтверждения языка дело не доводим, иначе «ru» залипает
            # в peer_lang_confirmed и ломает следующие фразы.
            alt = self._fallback_peer_lang("", text, allow_guess=True)
            if alt:
                log("[engine] распознано как ru, но текст без кириллицы — "
                    f"перевожу как {alt}")
                self._peer_lang_prob = prob
                return text, alt
        accepted, reason = self._detect_peer_lang(detected, prob, dur, words)
        if not accepted:
            # Раньше фраза выбрасывалась целиком. В живой сессии это стоило
            # 8 реплик из 12: определение языка колеблется на коротких и
            # шумных фразах, а собеседник слышал тишину. Теперь смена языка
            # по-прежнему требует подтверждения, но сама фраза переводится
            # уже подтверждённым языком — терять её хуже, чем перевести.
            fallback = self._fallback_peer_lang(detected, text)
            if fallback:
                log(f"[engine] язык не подтверждён ({reason}) — "
                    f"перевожу как {fallback}")
                self._peer_lang_prob = prob
                return text, fallback
            self._asr_skip = "lang"
            log(f"[engine] язык собеседника не подтверждён ({reason}) и "
                f"перевести нечем — фразу не перевожу")
            return "", self.peer_lang
        lang = self.peer_lang_confirmed or detected
        if lang == "ru" and _cyrillic_share(text) < 0.5:
            # Whisper иногда «узнаёт» русский в испанской речи. Раньше такой
            # текст уходил в озвучку без перевода (mt_ms=0) — отсюда «перевёл
            # совсем не туда». Для русского собеседника кириллица есть, и
            # этот путь не срабатывает.
            alt = self._fallback_peer_lang("", text, allow_guess=True)
            if alt:
                log("[engine] распознано как ru, но текст без кириллицы — "
                    f"перевожу как {alt}")
                self._peer_lang_prob = prob
                return text, alt
        self._peer_lang_prob = prob
        return text, lang

    def _detect_peer_lang(self, detected: str, prob: float, dur: float,
                          words: int) -> tuple[bool, str]:
        """Подтвердить язык собеседника (режим auto).

        Не переключаемся по одному короткому слову и по неуверенному
        определению: нужны фраза достаточной длины, уверенность не ниже
        PEER_LANG_MIN_CONF и (для смены языка) второе совпадение в течение
        2 минут. Последний подтверждённый язык сохраняется.
        """
        now = time.time()
        self._lang_hits = [(c, t) for (c, t) in self._lang_hits
                           if now - t < 120]
        payload = {"detected": detected, "prob": round(prob, 2),
                   "confirmed": self.peer_lang_confirmed,
                   "duration": round(dur, 2), "words": words}

        def reject(reason: str) -> tuple[bool, str]:
            log(f"[engine] язык: {detected} ({prob:.2f}, {dur:.2f}с, "
                f"{words} слов) — {reason}")
            emit({"event": "peer_lang_detected", **payload,
                  "accepted": False, "reason": reason})
            return False, reason

        if not detected or detected == "auto":
            return reject("язык не определён")
        # Язык уже подтверждён ранее — принимаем и короткую реплику.
        # Раньше пороги «длительность/слова» проверялись первыми, и после
        # одной удачной фразы следующие («Sí, claro», «Vale») отбрасывались
        # с «мало слов», и диалог обрывался.
        if self.peer_lang_confirmed and detected == self.peer_lang_confirmed:
            emit({"event": "peer_lang_detected", **payload,
                  "accepted": True, "reason": "язык уже подтверждён"})
            return True, "ok"
        if dur < self._peer_lang_min_sec:
            return reject(f"короткий фрагмент ({dur:.1f} < "
                          f"{self._peer_lang_min_sec:.1f} с)")
        if words < self._peer_lang_min_words:
            return reject("слишком мало слов для уверенного определения")
        if prob < PEER_LANG_MIN_CONF:
            return reject(f"низкая уверенность ({prob:.2f} < "
                          f"{PEER_LANG_MIN_CONF:.2f})")
        if detected == self.peer_lang_confirmed:
            emit({"event": "peer_lang_detected", **payload,
                  "accepted": True, "reason": "язык подтверждён"})
            return True, "ok"

        hits = [c for (c, _t) in self._lang_hits if c == detected]
        self._lang_hits.append((detected, now))
        switched = bool(self.peer_lang_confirmed)
        if switched and not hits:
            emit({"event": "peer_lang_detected", **payload, "accepted": False,
                  "reason": "смена языка не подтверждена (1 из 2)"})
            log(f"[engine] возможная смена языка на {detected}, ждём "
                f"подтверждения")
            return False, "смена языка не подтверждена"
        self.peer_lang_confirmed = detected
        self._peer_lang_prob = prob
        log(f"[engine] язык собеседника подтверждён: {detected} "
            f"({prob:.2f}), маршрут -> ru")
        emit({"event": "peer_lang", "code": detected, "auto": True,
              "prob": round(prob, 2), "switched": switched})
        emit({"event": "peer_lang_detected", **payload, "accepted": True,
              "reason": "язык подтверждён"})
        return True, "ok"

    def _fallback_peer_lang(self, detected: str, text: str,
                            allow_guess: bool = False) -> str:
        """Каким языком перевести фразу, если auto не подтвердил новый.

        Приоритет — уже подтверждённый язык собеседника: он не прыгает от
        одной короткой реплики. Если его нет — определённый, лишь бы для
        него была модель. «ru» здесь не годится: это язык пользователя, и
        переводить с него нечего.
        """
        for code in (self.peer_lang_confirmed, detected):
            if code and code not in ("auto", "ru") \
                    and self.reverse_available(code):
                return code
        if not allow_guess or _cyrillic_share(text) >= 0.5:
            return ""
        # Совсем нет зацепок, а текст явно не русский: берём недавно
        # определённый язык с моделью, иначе испанский (типовой собеседник).
        recent = [c for (c, _t) in reversed(self._lang_hits)
                  if c not in ("", "auto", "ru") and self.reverse_available(c)]
        if recent:
            return recent[0]
        if self.reverse_available("es"):
            return "es"
        return ""

    # ---------- проверка синтеза ----------
    def verify(self, audio: np.ndarray, expected: str) -> float:
        """Насколько сказанное соответствует ожидаемому (0..1).

        Whisper уже загружен для распознавания — используем его же, чтобы
        отбрасывать «мусорные» варианты синтеза (на коротких фразах XTTS
        иногда выдаёт мусор: «¿Qué tal mi juego?» -> «¡Titan Michuevo!»).

        Сравниваем ПОСИМВОЛЬНО, а не по словам: XTTS часто произносит
        верное, но Whisper записывает иначе («Oyen el ruso o no?» ->
        «Hoy en el Rusono») — это фонетически одно и то же, и отбрасывать
        такой вариант нельзя.
        """
        if self.asr is None or audio.size == 0 or not expected.strip():
            return 1.0
        try:
            segs, _ = self.asr.transcribe(
                audio.astype(np.float32), language=xtts_language(self.lang),
                beam_size=1, vad_filter=False, condition_on_previous_text=False)
            heard = " ".join(s.text.strip() for s in segs).strip()
        except Exception:
            return 1.0
        if not heard:
            return 0.0
        import difflib
        import re

        def norm(t: str) -> str:
            t = re.sub(r"[¿?¡!.,]", " ", t.lower())
            return " ".join(t.split())
        return difflib.SequenceMatcher(None, norm(expected),
                                       norm(heard)).ratio()

    # ---------- синтез потоком ----------
    def _emit_chunk(self, part: np.ndarray, seq: int) -> None:
        """Отдать кусок аудио в GUI (base64 int16)."""
        t0 = getattr(self, "_out_t0", None)
        if t0 is not None and not getattr(self, "_out_first_sent", False):
            self._out_first_sent = True
            emit({"event": "metrics", "dir": "out_tts",
                  "tts_first_ms": int((time.time() - t0) * 1000),
                  "seq": seq, "queue": len(self._queue_len()),
                  "dropped": self.dropped, "cancelled": self.cancelled})
        pcm = (np.clip(part, -1.0, 1.0) * 32767).astype(np.int16)
        emit({"event": "chunk", "seq": seq,
              "pcm": base64.b64encode(pcm.tobytes()).decode("ascii")})

    def _log_phrase(self, **fields) -> None:
        """Одна строка таймингов фразы — в лог и в отчёт.

        Поля: dir (in/out), seq, lang, wait_ms (очередь до ASR), asr_ms,
        mt_ms, gate_ms (ожидание замка XTTS), first_ms (первый чанк),
        tts_ms (синтез целиком), total_ms (от конца речи до последнего чанка).
        """
        parts = [f"{k}={v}" for k, v in fields.items() if v is not None]
        log("[phrase] " + " ".join(parts))
        emit({"event": "phrase_timing", **fields})

    def _take_phrase_timing(self, text: str) -> dict:
        """Тайминги ASR/MT именно этой фразы (сверху очереди ожидания)."""
        if not self._pending_timings:
            return {}
        info = self._pending_timings[0]
        if (info.get("ru") or "").strip() != (text or "").strip():
            return {}
        self._pending_timings.pop(0)
        return info

    def _emit_incoming_chunk(self, part: np.ndarray, seq: int) -> None:
        """Отдать кусок входящего аудио в GUI (base64 int16, 24 кГц).

        Идёт в отдельный event incoming_chunk, чтобы GUI мог разделить
        исходящий перевод (в кабель) и входящий (в наушники).
        """
        pcm = (np.clip(part, -1.0, 1.0) * 32767).astype(np.int16)
        emit({"event": "incoming_chunk", "seq": seq,
              "pcm": base64.b64encode(pcm.tobytes()).decode("ascii")})

    def _synth_full(self, spoken: str, params: dict, seed: int,
                    lang: str | None = None) -> np.ndarray:
        """Синтезировать фразу целиком (numpy float32)."""
        try:
            import torch
            torch.manual_seed(seed)
        except Exception:
            pass
        # XTTS — одна модель в памяти на оба направления. Без блокировки
        # входящая озвучка (свой поток) и исходящая лезли в неё
        # одновременно: часть фраз озвучивалась битым звуком или молча.
        with self.lock:
            chunks = self.tts.inference_stream(
                spoken, xtts_language(lang or self.lang), self.gpt_latent,
                self.spk_emb, stream_chunk_size=self.stream_chunk,
                overlap_wav_len=2048, **params)
            parts = [c.detach().cpu().numpy() for c in chunks]
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts).astype(np.float32)

    # ---------- Piper: озвучка языков, которых нет в XTTS ----------

    def _piper_voice_path(self, voice_id: str) -> str | None:
        """УДАЛЕНО: Piper больше не используется (мегрельский убран).

        Оставлен как заглушка, чтобы старые вызовы не падали.
        """
        return None

    def _piper_synth(self, text: str, voice_id: str):
        """УДАЛЕНО: Piper больше не используется."""
        import numpy as np
        return np.zeros(0, dtype=np.float32)

    def _uses_piper(self) -> bool:
        """Всегда False: Piper удалён вместе с мегрельским."""
        return False

    def speak(self, text: str, seq: int = 0, ru: str = "",
              lang: str | None = None) -> None:
        """Синтезировать перевод своим голосом, отдавая чанки.

        Для языков, которых нет в XTTS (например, мегрельский), используется
        Piper с готовым голосом — клона там технически получить нельзя.

        Подача зависит от ТОНА фразы (тон определяется по РУССКОМУ тексту —
        перевод эмоцию смягчает): ругательство звучит злее и резче,
        приветствие — теплее (tools/voice_tone.py).

        Две особенности:
        * ПАУЗЫ — в переводе их нет, и XTTS читает длинную фразу одним
          потоком («монотонно»). Ставим запятые по смыслу.
        * КОРОТКИЕ фразы XTTS ломает (иногда «¿Qué tal mi juego?» ->
          «¡Titan Michuevo!»), поэтому их синтез проверяется тем же
          Whisper и при неудаче повторяется с другим seed. Длинные
          фразы не ломаются — их отдаём потоком, не теряя задержку.
        """
        if not text.strip():
            emit({"event": "done", "seq": seq, "ms": 0})
            return
        t0 = time.time()

        # Языки, которых нет в XTTS (мегрельский/грузинский) — Piper
        if self._uses_piper():
            voice_id = voice_lang.piper_voice(self.lang)
            audio = self._piper_synth(text, voice_id)
            if audio.size:
                for part in np.array_split(audio, max(1, len(audio) // 12000)):
                    self._emit_chunk(part, seq)
            else:
                log(f"[engine] Piper не дал звука для языка {self.lang}")
            emit({"event": "done", "seq": seq,
                  "ms": int((time.time() - t0) * 1000)})
            return

        # язык синтеза: по умолчанию язык перевода, но можно озвучить
        # текст и на другом языке XTTS (предпрослушивание голоса)
        tts_code = lang or self.lang
        tone, params = _tone_params(text, ru, self.liveliness)
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import voice_tone
            import voice_post
            spoken = voice_post.add_pauses(
                voice_tone.apply_punctuation(text, tone))
        except Exception:
            spoken = text
        if spoken != text:
            log(f"[engine] пунктуация/паузы: {text!r} -> {spoken!r}")
        log(f"[engine] тон: {tone}, живость: {self.liveliness} -> "
            f"temp={params['temperature']}, speed={params['speed']}")
        # Запоминаем, что сказали сами: по этому отсекаем собственный голос
        # в перехвате (перевод идёт и в наушники, и в запись игры).
        self.last_spoken.append((spoken, time.time()))
        del self.last_spoken[:-5]

        short = len(text.split()) <= 6

        # Длинные фразы всегда идут потоком. Короткие — тоже, если режим
        # это разрешает: полный синтез + проверка распознаванием задерживали
        # первый звук на ~0,6 с (замер: 1111 мс против 481 мс у длинных).
        if not short or self.stream_short:
            self._stream_speak(spoken, params, seq, tts_code)
            return

        # короткая фраза в Quality/Manual: целиком, с проверкой и обработкой
        audio = np.zeros(0, dtype=np.float32)
        for attempt in range(1 + self.verify_attempts):
            audio = self._synth_full(spoken, params, 1234 + attempt * 7919,
                                     lang=tts_code)
            if audio.size == 0:
                break
            score = self.verify(audio, text)
            log(f"[engine] попытка {attempt + 1}: совпадение {score:.0%}")
            if score >= 0.55:
                break
        if audio.size:
            try:
                import voice_post
                audio = voice_post.add_life(audio, SR_TTS, tone, spoken)
            except Exception:
                pass
            for part in np.array_split(audio, max(1, len(audio) // 12000)):
                self._emit_chunk(part, seq)
        total_ms = int((time.time() - t0) * 1000)
        self._log_phrase(dir="out", seq=seq, gate_ms=self.lock.wait_ms,
                         first_ms=total_ms, tts_ms=total_ms,
                         total_ms=total_ms)
        emit({"event": "done", "seq": seq, "ms": int((time.time() - t0) * 1000)})

    def _stream_speak(self, spoken: str, params: dict, seq: int,
                      tts_code: str) -> None:
        """Синтез потоком: отдали кусок — сразу в кабель.

        Без полного синтеза, проверки распознаванием и `add_life`: именно
        они держали первый звук до конца фразы. Проверка остаётся в
        Quality/Manual, где задержка не главное.
        """
        t0 = time.time()
        first_ms = None
        try:
            import torch
            # Вариативный seed: фиксированный 1234 давал монотонность.
            self._seed_counter = getattr(self, "_seed_counter", 0) + 1
            seed = (abs(hash(spoken)) % 100000) + self._seed_counter * 7919
            torch.manual_seed(seed)
            # Блокировка на всё время синтеза: XTTS не является
            # потокобезопасным, а входящая (русская) озвучка идёт своим
            # потоком. Без неё часть фраз оставалась без звука.
            with self.lock:
                for c in self.tts.inference_stream(
                        spoken, xtts_language(tts_code), self.gpt_latent,
                        self.spk_emb, stream_chunk_size=self.stream_chunk,
                        overlap_wav_len=2048, **params):
                    if first_ms is None:
                        first_ms = int((time.time() - t0) * 1000)
                    self._emit_chunk(c.detach().cpu().numpy(), seq)
        except Exception as exc:
            log(f"[engine] синтез не удался: {type(exc).__name__}: {exc}")
        total_ms = int((time.time() - t0) * 1000)
        self._log_phrase(dir="out", seq=seq, gate_ms=self.lock.wait_ms,
                         first_ms=first_ms, tts_ms=total_ms,
                         total_ms=total_ms)
        emit({"event": "done", "seq": seq,
              "ms": int((time.time() - t0) * 1000)})

    def speak_incoming(self, text: str, seq: int = 0,
                       voice_profile: str | None = None) -> None:
        """Синтезировать русский текст (входящий перевод) через XTTS.

        Выдаёт чанки через incoming_chunk события — GUI направляет их
        в наушники (отдельный bus), а не в виртуальный микрофон.

        Запускается из главного цикла движка (не из _peer_loop), поэтому
        не блокирует обработку входящего аудио. Синтез выполняется в
        отдельном потоке, чтобы не задерживать другие команды IPC.
        """
        if not text.strip():
            emit({"event": "incoming_done", "seq": seq, "ms": 0})
            return
        # Синтез в отдельном потоке (не блокирует IPC), но СТРОГО по
        # очереди: голос один. Раньше на каждую фразу стартовал свой
        # поток, фраза N+1 запускалась, пока N ещё звучала, и GUI
        # выбрасывал её оставшиеся чанки как «устаревшие» — в истории
        # текст есть, а озвучки нет.
        with self._incoming_jobs_lock:
            if len(self._incoming_jobs) >= 3:
                # Отстали больше чем на три фразы — склеиваем последние
                # две: ничего не теряем и меньше отстаём.
                prev_text, prev_seq, prev_prof = self._incoming_jobs.pop()
                text = prev_text + " " + text.strip()
                seq = prev_seq
                voice_profile = prev_prof or voice_profile
            self._incoming_jobs.append((text, seq, voice_profile))
            if self._incoming_worker_on:
                return
            self._incoming_worker_on = True
        threading.Thread(target=self._incoming_worker, daemon=True).start()

    def _incoming_worker(self) -> None:
        """Озвучивать входящие фразы по одной, в порядке поступления."""
        while True:
            with self._incoming_jobs_lock:
                if not self._incoming_jobs:
                    self._incoming_worker_on = False
                    return
                text, seq, voice_profile = self._incoming_jobs.pop(0)
            try:
                self._synthesize_incoming(text, seq, voice_profile)
            except Exception as exc:  # noqa: BLE001
                log(f"[engine] входящая озвучка: {type(exc).__name__}: {exc}")
                emit({"event": "incoming_done", "seq": seq, "ms": 0})

    def _synthesize_incoming(self, text: str, seq: int,
                             voice_profile: str | None = None) -> None:
        """Выполнить синтез русского текста для входящего перевода.

        Использует тот же экземпляр XTTS, что и исходящий перевод,
        но с языком 'ru'. Голосовой профиль пользователя (если задан)
        игнорируется на этом этапе — используется клонированный голос
        пользователя (self.spk_emb / self.gpt_latent).

        Текст добавляется в last_spoken, чтобы перехват речи игроков
        не захватил свой синтезированный перевод (защита от аудиопетель).
        """
        # Тон и живость — как у исходящей речи. Раньше входящий перевод
        # синтезировался с ЖЁСТКО ЗАДАННЫМИ параметрами (temp=0.78, speed=0.97)
        # и без пунктуации по тону: ползунок «живость» на него не влиял
        # вообще, а злая реплика читалась ровно, как нейтральная. Отсюда
        # жалоба «слышно, что синтез».
        tone, params = _tone_params(text, "", self.liveliness)
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import voice_post
            import voice_tone
            spoken = voice_post.add_pauses(
                voice_tone.apply_punctuation(text, tone))
        except Exception:
            spoken = text
        if spoken != text:
            log(f"[engine] входящая пунктуация: {text!r} -> {spoken!r}")
        log(f"[engine] входящий тон: {tone}, живость: {self.liveliness} -> "
            f"temp={params['temperature']}, speed={params['speed']}")
        # Запоминаем, что синтезируем — для защиты от аудиопетель
        self.last_spoken.append((spoken, time.time()))
        del self.last_spoken[:-5]
        t0 = time.time()
        gen = self.gen
        first_ms = None
        info = self._take_phrase_timing(text)
        try:
            import torch
            # ВАРИАТИВНЫЙ seed: с фиксированным 1234 каждая фраза звучала
            # одинаково монотонно («неживо»). Берём seed от хэша текста и
            # счётчика — одинаковые фразы не повторяются точь-в-точь.
            self._seed_counter = getattr(self, "_seed_counter", 0) + 1
            seed = (abs(hash(spoken)) % 100000) + self._seed_counter * 7919
            torch.manual_seed(seed)
            # Входящая озвучка — низкий приоритет: если пользователь начал
            # говорить, исходящий синтез пройдёт раньше следующей фразы.
            with self.lock.hold(_TtsGate.PRIO_IN):
                for c in self.tts.inference_stream(
                        spoken, "ru", self.gpt_latent, self.spk_emb,
                        stream_chunk_size=self.stream_chunk,
                        overlap_wav_len=2048, **params):
                    if gen != self.gen:
                        # язык/режим сменились — старый перевод не озвучиваем
                        self.cancelled += 1
                        log("[engine] входящий синтез устарел — оборван")
                        break
                    if first_ms is None:
                        first_ms = int((time.time() - t0) * 1000)
                        emit({"event": "metrics", "dir": "in_tts",
                              "tts_first_ms": first_ms, "seq": seq,
                              "queue": self._peer_q.qsize(),
                              "dropped": self.dropped,
                              "cancelled": self.cancelled})
                    self._emit_incoming_chunk(c.detach().cpu().numpy(), seq)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] синтез входящего не удался: "
                f"{type(exc).__name__}: {exc}")
        tts_ms = int((time.time() - t0) * 1000)
        total_ms = tts_ms
        if info.get("arrival"):
            # «фраза целиком»: от получения последнего куска речи
            total_ms = int((time.time() - info["arrival"]) * 1000)
        self._log_phrase(dir="in", seq=seq, lang=info.get("lang"),
                         wait_ms=info.get("wait_ms"),
                         asr_ms=info.get("asr_ms"), mt_ms=info.get("mt_ms"),
                         gate_ms=self.lock.wait_ms, first_ms=first_ms,
                         tts_ms=tts_ms, total_ms=total_ms)
        emit({"event": "incoming_done", "seq": seq, "ms": tts_ms})


def main() -> None:
    global LOG_FILE

    engine = Engine()
    reference = ""
    for arg in sys.argv[1:]:
        if arg.startswith("--reference="):
            reference = arg.split("=", 1)[1]
    engine.reference = reference

    # Свой лог: в EXE консоли нет, а stderr может не доехать
    try:
        logs = os.path.join(os.path.dirname(reference), "logs")
        os.makedirs(logs, exist_ok=True)
        LOG_FILE = os.path.join(logs, "live_engine.log")
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write(f"=== запуск движка {time.strftime('%H:%M:%S')} ===\n")
            fh.write(f"reference={reference}\n")
    except Exception as exc:
        print(f"не удалось создать лог: {exc}", file=sys.stderr, flush=True)

    log(f"[engine] старт: reference={reference}, протокол {PROTOCOL_VERSION}")
    # protocol — чтобы GUI заметил движок от другой сборки и предупредил.
    emit({"event": "boot", "protocol": PROTOCOL_VERSION,
          "pid": os.getpid()})

    def refresh_catalog_job() -> None:
        """Обновить каталог HuggingFace в фоне (сеть, без блокировки IPC)."""
        try:
            import model_discovery
            res = model_discovery.refresh(user_lang=engine.src_lang or "ru")
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "found": 0,
                   "error": f"{type(exc).__name__}: {exc}"}
        emit({"event": "catalog_refreshed", **res})
        try:
            emit({"event": "catalog", "models": engine.catalog(),
                  "loaded": engine.loaded})
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] каталог после обновления не собран: {exc}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:
            emit({"event": "error", "message": f"плохой JSON: {exc}"})
            continue

        cmd = msg.get("cmd")
        log(f"[engine] команда: {cmd}")
        try:
            if cmd == "load":
                t0 = time.time()
                engine.load(reference)
                emit({"event": "ready", "load_ms": int((time.time() - t0) * 1000),
                      "asr_ms": engine.load_ms})
            elif cmd == "reference":
                ok = engine.set_reference(msg.get("path", ""))
                emit({"event": "reference", "ok": bool(ok),
                      "path": msg.get("path", "")})
            elif cmd == "speak":
                engine.speak(msg.get("text", ""), msg.get("seq", 0),
                             lang=msg.get("lang"))
            elif cmd == "lang":
                # язык перевода: es / en / ow (олдвест) / it
                code = engine.set_lang(msg.get("code", "es"))
                emit({"event": "lang", "code": code,
                      "title": _lang_info(code)["title"]})
            elif cmd == "peer_lang":
                # язык чужой речи: auto или конкретный
                code = engine.set_peer_lang(msg.get("code", "auto"))
                emit({"event": "peer_lang", "code": code})
            elif cmd == "set_auto_download":
                # автоскачивание пакетов (по умолчанию выключено)
                engine.auto_download = bool(msg.get("on", False))
                log(f"[engine] автоскачивание пакетов: "
                    f"{'вкл' if engine.auto_download else 'выкл'}")
                emit({"event": "auto_download", "on": engine.auto_download})
            elif cmd == "src_lang":
                # язык пользователя (источник исходящего перевода)
                code = engine.set_src_lang(msg.get("code", "ru"))
                emit({"event": "src_lang", "code": code})
            elif cmd == "models":
                # что реально установлено (ASR/TTS/MT) — для интерфейса
                emit({"event": "models", **engine.models_info()})
            elif cmd == "catalog":
                # каталог моделей с состоянием установки/загрузки
                emit({"event": "catalog", "models": engine.catalog(),
                      "loaded": engine.loaded})
            elif cmd == "refresh_catalog":
                # обновляемый список с HuggingFace (размеры, железо)
                threading.Thread(target=refresh_catalog_job,
                                 daemon=True).start()
            elif cmd == "model_download":
                repos = [r for r in (msg.get("models")
                                     or [msg.get("id", "")]) if r]
                req = msg.get("request") or msg.get("id") or ",".join(repos)
                threading.Thread(
                    target=engine.download_repos,
                    args=(repos, req, msg.get("label", "")),
                    daemon=True).start()
            elif cmd == "model_cancel":
                engine.cancel_download(msg.get("request", ""))
            elif cmd == "model_remove":
                res = engine.remove_model(msg.get("id", ""))
                emit({"event": "model_removed", **res})
            elif cmd == "model_verify":
                res = engine.verify_repo(msg.get("id", ""))
                emit({"event": "verify", **res})
            elif cmd == "model_select":
                res = engine.select_model(msg.get("kind", ""),
                                          msg.get("id", ""))
                emit({"event": "model_selected", **res})
            elif cmd == "packs":
                emit({"event": "packs", "packs": engine.packs(),
                      "user_lang": engine.src_lang})
            elif cmd == "pack_install":
                threading.Thread(
                    target=engine.pack_install,
                    args=(msg.get("code", ""), msg.get("request", "")),
                    daemon=True).start()
            elif cmd == "pack_remove":
                engine.pack_remove(msg.get("code", ""))
            elif cmd == "pack_verify":
                code = msg.get("code", "")
                pack = next((p for p in engine.packs()
                             if p["code"] == code), None)
                bad = []
                for m in (pack or {}).get("models", []):
                    chk = engine.verify_repo(m["id"])
                    if not chk["ok"]:
                        bad.append({"id": m["id"], "missing": chk["missing"]})
                emit({"event": "pack_verify", "code": code,
                      "ok": not bad, "problems": bad})
            elif cmd == "models_load":
                engine.load(engine.reference or reference)
                emit({"event": "ready", "asr_ms": engine.load_ms})
            elif cmd == "models_unload":
                engine.unload_models()
                emit({"event": "unloaded", "rss_mb": round(_rss_mb(), 1)})
            elif cmd == "set_asr":
                # переключение модели распознавания (только установленной)
                name = engine.set_asr(msg.get("name", ""))
                engine._bump_gen(f"ручной выбор ASR {name}")
                emit({"event": "asr", "name": name})
            elif cmd == "mode":
                # режим Fast / Balanced / Quality / Manual
                engine.set_mode(msg.get("code", "balanced"))
            elif cmd == "stats":
                # диагностика: RAM/VRAM/очереди/счётчики
                emit({"event": "stats", **engine.stats()})
            elif cmd == "peer":
                # фрагмент звука игры -> разбор речи игроков
                pcm = base64.b64decode(msg.get("pcm", ""))
                phrase = msg.get("phrase")
                engine.push_peer_pcm(
                    pcm, int(msg.get("sr", SR_ASR)),
                    bool(msg.get("partial")), bool(msg.get("last", True)),
                    None if phrase is None else int(phrase))
            elif cmd == "liveliness":
                # уровень живости от пользователя (0 — ровно, 3 — максимум)
                engine.liveliness = max(0, min(3, int(msg.get("level", 2))))
                log(f"[engine] живость: {engine.liveliness}")
            elif cmd == "translate":
                # аудио -> текст RU -> текст ES -> озвучка
                pcm = base64.b64decode(msg.get("pcm", ""))
                sr = int(msg.get("sr", SR_ASR))
                floor = float(msg.get("floor", 0.0))
                engine._out_t0 = time.time()
                engine._out_first_sent = False
                t0 = time.time()
                ru = engine.transcribe(pcm, sr, floor)
                t_asr = int((time.time() - t0) * 1000)
                t0 = time.time()
                es = engine.translate_text(ru)
                t_tr = int((time.time() - t0) * 1000)
                log(f"[engine] ASR({t_asr}мс): {ru}")
                log(f"[engine] ES({t_tr}мс): {es}")
                # тон считаем заранее, чтобы показать его в интерфейсе
                try:
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    import voice_tone
                    tone = voice_tone.detect_tone_pair(ru, es)
                except Exception:
                    tone = "neutral"
                emit({"event": "text", "ru": ru, "es": es, "tone": tone,
                      "asr_ms": t_asr, "tr_ms": t_tr})
                # русский текст передаём, чтобы тон определялся по нему:
                # перевод эмоцию смягчает («ублюдки» -> «¿Qué tal mi juego?»)
                engine.speak(es, msg.get("seq", 0), ru)
            elif cmd == "incoming_speak":
                # Входящий перевод: синтез русского текста в наушники.
                engine.speak_incoming(msg.get("text", ""), msg.get("seq", 0),
                                      msg.get("voice_profile"))
            elif cmd == "quit":
                break
            elif cmd == "unload":
                # Явная выгрузка моделей БЕЗ завершения процесса.
                # Раньше при «Остановить модель» процесс просто убивался, и
                # Windows освобождала память с задержкой — 5+ ГБ оставались
                # занятыми. Теперь движок чистит ссылки и вызывает gc.
                engine.unload_models()
                emit({"event": "unloaded",
                      "rss_mb": round(_rss_mb(), 1)})
            else:
                emit({"event": "error", "message": f"неизвестная команда: {cmd}"})
        except Exception as exc:  # noqa: BLE001
            import traceback
            emit({"event": "error", "message": f"{type(exc).__name__}: {exc}",
                  "traceback": traceback.format_exc()})
            log(traceback.format_exc())
    log("[engine] завершение")


if __name__ == "__main__":
    main()
