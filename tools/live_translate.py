"""Живой перевод RU->ES: движок, который держит модели в памяти.

GUI (RedZVoiceStudio.exe) не содержит torch — тяжёлые модели живут в движке
(%LOCALAPPDATA%\\RedZVoiceStudio\\engine). Этот скрипт — серверная часть
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
import queue
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


def _lang_info(code: str) -> dict:
    """Параметры языка (если модуль недоступен — только испанский)."""
    if voice_lang is None:
        return {"title": "Испанский", "xtts": "es",
                "mt": ["Helsinki-NLP/opus-mt-ru-es"], "field": "es"}
    return voice_lang.info(code)


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
ASR_MODEL = os.environ.get("REDZ_ASR_MODEL", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
ASR_FALLBACK = os.environ.get("REDZ_ASR_FALLBACK", "Systran/faster-whisper-small")

# Точность вычислений для распознавания:
#   float16      — VRAM 2241 МБ
#   int8_float16 — тот же текст на записях пользователя, VRAM 1019 МБ
#                  (минус ~1.2 ГБ — важно, когда параллельно игра)
# Замер: research/bench_optimization.py, research/bench_int8_quality.py
ASR_COMPUTE = os.environ.get("REDZ_ASR_COMPUTE", "int8_float16")

# Перевод на CPU: он занимает 0.6 ГБ VRAM и совсем немного GPU.
# Разница по скорости — 147 мс против 77 мс, зато видеопамять вся
# остаётся игре и XTTS.
MT_DEVICE = os.environ.get("REDZ_MT_DEVICE", "cpu")

# Размер чанка XTTS: чем меньше, тем раньше появляется первый звук.
# Важно, когда GPU занят игрой.
STREAM_CHUNK = int(os.environ.get("REDZ_STREAM_CHUNK", "10"))

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
        # уровень живости сдвигает параметры, но не ломает потолок
        level = max(0, min(3, int(liveliness)))
        boost = (level - 2) * 0.04
        params["temperature"] = round(min(0.85,
                                         params.get("temperature", 0.75) + boost), 3)
        params["top_p"] = round(min(0.94,
                                    params.get("top_p", 0.88) + boost * 0.25), 3)
        params["top_k"] = max(1, min(90, int(params.get("top_k", 60)
                                          * (1 + boost))))
        params["speed"] = round(params.get("speed", 1.02) + boost * 0.2, 3)
        params["repetition_penalty"] = max(3.0, min(9.0,
                                                    params.get("repetition_penalty",
                                                               5.0) - boost * 10))
        # top_k/top_p XTTS не принимает 0 — подстраховка
        params["top_k"] = max(1, int(params.get("top_k", 60)))
        params["top_p"] = min(0.99, max(0.01, float(params.get("top_p", 0.88))))
        return tone, params
    except Exception as exc:  # noqa: BLE001
        log(f"[engine] тон не определён ({type(exc).__name__}: {exc})")
        return "neutral", {"temperature": 0.75, "top_p": 0.88, "top_k": 60,
                           "speed": 1.02, "repetition_penalty": 5.0}


def is_hallucination(text: str) -> bool:
    """Похоже ли это на галлюцинацию Whisper (текст из тишины/шума)?

    Whisper на шуме и тишине выдаёт заготовки: «Субтитры сделал…»,
    «Продолжение следует…», «Спасибо за просмотр» и т.п. Их озвучивать нельзя.
    """
    if not text:
        return True
    low = text.lower().strip()
    if len(low) < 4:
        return True
    markers = (
        "субтитры", "продолжение следует", "спасибо за просмотр",
        "дimaторзок", "dimatorzok", "субтитры сделал", "www.", "http",
        "thanks for watching", "подписывайтесь", "лайк", "комментарий",
        "постарше", "мне нужно", "ты не знаешь", "я не знаю, что это",
        "пожалуйста, послушайте", "кхм",
    )
    return any(m in low for m in markers)


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


class Engine:
    """Модели и логика перевода. Загружаются один раз и живут в памяти."""

    def __init__(self) -> None:
        self.asr = None
        self.mt_tok = None
        self.mt = None
        self.tts = None
        self.gpt_latent = None
        self.spk_emb = None
        self.lock = threading.Lock()
        self.load_ms = 0
        # Уровень живости (0 — ровно, 3 — максимум). Пользователь задаёт
        # ползунком; тон фразы сдвигает параметры поверх него.
        self.liveliness = 2
        # Язык перевода: es (по умолчанию), en, ow (олдвест), it
        self.lang = "es"
        # Кэш моделей перевода: код -> (токенизатор, модель).
        # Держим не больше двух (текущий + испанский), чтобы не съедать RAM.
        self._mt_cache: dict[str, list] = {}
        # ---------- перехват речи других игроков ----------
        self._peer_q: "queue.Queue" = queue.Queue(maxsize=8)
        self._peer_thread: threading.Thread | None = None
        # Язык чужой речи: "auto" (определяем сами) или es/en/it/ru
        self.peer_lang = "auto"
        # Последнее, что мы САМИ сказали в игру — по нему отсекаем
        # собственный голос, попавший в перехват из наушников.
        self.last_spoken: list[str] = []

    # ---------- загрузка ----------
    def load(self, reference: str) -> None:
        import torch
        from faster_whisper import WhisperModel
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        t0 = time.time()
        # распознавание: пробуем лёгкую модель, при неудаче — тяжёлую
        # ASR_COMPUTE: float16 (качество) или int8_float16 (экономия VRAM).
        # Замер: int8_float16 даёт тот же текст, но VRAM 2241 -> 1019 МБ
        # и распознавание в ~2.4 раза быстрее.
        self.asr = None
        for name in (ASR_MODEL, ASR_FALLBACK):
            try:
                self.asr = WhisperModel(name, device="cuda",
                                        compute_type=ASR_COMPUTE)
                log(f"[engine] распознавание: {name} ({ASR_COMPUTE})")
                break
            except Exception as exc:  # noqa: BLE001
                log(f"[engine] не удалось загрузить {name}: {exc}")
        if self.asr is None:
            raise RuntimeError("не удалось загрузить модель распознавания")

        # перевод: по умолчанию на CPU — освобождаем видеопамять для игры
        self._mt_for(self.lang)
        self.load_ms = int((time.time() - t0) * 1000)
        log(f"[engine] ASR + перевод загружены за {self.load_ms} мс "
            f"(перевод на {MT_DEVICE})")

        # Поток перехвата чужой речи (стартует сразу, но звук приходит
        # только когда приложение его присылает).
        if self._peer_thread is None:
            self._peer_thread = threading.Thread(target=self._peer_loop,
                                                 daemon=True)
            self._peer_thread.start()

        self._load_tts(reference)

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
        if code not in ("es", "en", "ow", "it"):
            log(f"[engine] неизвестный язык: {code!r}")
            return self.lang
        try:
            self._mt_for(code)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] не удалось загрузить перевод для {code}: "
                f"{type(exc).__name__}: {exc}")
            return self.lang
        self.lang = code
        log(f"[engine] язык перевода: {code} ({info['title']}), "
            f"XTTS: {info['xtts']}")
        return self.lang

    def _mt_for(self, code: str) -> list[tuple]:
        """Модели перевода ru -> язык (грузятся при первом обращении).

        Возвращает список пар (токенизатор, модель) — это цепочка: для
        итальянского это ru->es->it (прямой модели ru->it не существует).
        """
        return self._load_chain(f"chain:{code}", _mt_names(code))

    def _mt_reverse(self, src: str) -> list[tuple]:
        """Модели перевода язык -> русский (для чужих игроков)."""
        names = _reverse_mt_names(src)
        if not names:
            return []
        return self._load_chain(f"rev:{src}", names)

    def _load_chain(self, key: str, names: list[str]) -> list[tuple]:
        """Загрузить (и закэшировать) цепочку моделей перевода."""
        if key in self._mt_cache:
            return self._mt_cache[key]
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        t0 = time.time()
        chain = []
        for name in names:
            tok = AutoTokenizer.from_pretrained(name)
            dtype = torch.float16 if MT_DEVICE == "cuda" else torch.float32
            model = AutoModelForSeq2SeqLM.from_pretrained(
                name, dtype=dtype).to(MT_DEVICE).eval()
            chain.append((tok, model))
        # Кэш: не больше двух языков (текущий + испанский) — RAM конечен.
        if len(self._mt_cache) >= 2 and key not in self._mt_cache:
            keep = {key}
            if "chain:es" in self._mt_cache and key != "chain:es":
                keep.add("chain:es")
            for k in list(self._mt_cache):
                if k not in keep:
                    del self._mt_cache[k]
                    log(f"[engine] модель перевода {k} выгружена из памяти")
        self._mt_cache[key] = chain
        self.mt_tok, self.mt = chain[0]
        log(f"[engine] модель перевода {' -> '.join(names)} загружена за "
            f"{int((time.time() - t0) * 1000)} мс")
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

        # кэш голоса: считается один раз (1.4 с), дальше 0.03 с
        self.gpt_latent, self.spk_emb = self.tts.get_conditioning_latents(
            audio_path=[reference])
        log(f"[engine] XTTS + кэш голоса за {(time.time() - t0) * 1000:.0f} мс")

    # ---------- перевод текста ----------
    def _run_chain(self, text: str, chain: list[tuple]) -> str:
        """Прогнать текст по цепочке моделей перевода."""
        import torch
        for tok, model in chain:
            batch = tok([text], return_tensors="pt", padding=True).to(MT_DEVICE)
            with torch.inference_mode():
                out = model.generate(**batch, max_new_tokens=128, num_beams=1)
            text = tok.batch_decode(out, skip_special_tokens=True)[0].strip()
        return text

    def translate_text(self, ru: str) -> str:
        if not ru.strip():
            return ""
        chain = self._mt_for(self.lang)
        text = self._run_chain(ru, chain)
        # Олдвест: это английский, переписанный словами ковбойской речи.
        # Лишней модели и задержки это не добавляет.
        if self.lang == "ow" and voice_lang is not None:
            text = voice_lang.to_oldwest(text)
        return text

    def translate_to_ru(self, text: str, src: str) -> str:
        """Перевести чужую речь на русский (перехват игроков)."""
        if not text.strip() or src == "ru":
            return text
        chain = self._mt_reverse(src)
        if not chain:
            return text
        try:
            return self._run_chain(text, chain)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] перевод {src}->ru не удался: "
                f"{type(exc).__name__}: {exc}")
            return text

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

        # Проверка уровня: фрагмент должен быть заметно громче шума.
        if floor > 0.0005:
            seg_rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
            if seg_rms < floor * 2.2:
                log(f"[engine] фрагмент тише шума ({seg_rms:.4f} < {floor * 2.2:.4f}) "
                    f"— пропускаю")
                return ""

        # Микрофон тихий (RMS ~0.01), а Whisper ждёт нормальный уровень:
        # на тихом звуке он часто НИЧЕГО не узнаёт. Нормализуем.
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 1e-4:
            audio = audio / peak * 0.7

        # no_speech_threshold/log_prob_threshold — отсекаем пустые сегменты
        segs, _ = self.asr.transcribe(
            audio, language="ru", beam_size=1, vad_filter=False,
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
        """Язык чужой речи: auto (определяем) или es/en/it/ru."""
        code = (code or "auto").lower().strip()
        self.peer_lang = code if code in ("auto", "es", "en", "it", "ru") else "auto"
        log(f"[engine] язык чужой речи: {self.peer_lang}")
        return self.peer_lang

    def push_peer_pcm(self, pcm_bytes: bytes, sr: int = SR_ASR) -> bool:
        """Отдать фрагмент звука игры на разбор (что говорят игроки)."""
        if not pcm_bytes:
            return False
        try:
            self._peer_q.put_nowait((pcm_bytes, sr))
        except queue.Full:
            # очередь переполнена — пропускаем фрагмент (лучше потерять
            # реплику, чем копить задержку)
            return False
        return True

    def _peer_loop(self) -> None:
        """Поток разбора чужой речи: звук -> текст -> перевод на русский."""
        while True:
            try:
                pcm, sr = self._peer_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                text, lang = self.transcribe_peer(pcm, sr)
                if not text:
                    continue
                if self._is_own_voice(text):
                    log(f"[engine] перехват: это наш собственный голос, "
                        f"пропускаю ({text!r})")
                    continue
                ru = self.translate_to_ru(text, lang)
                emit({"event": "peer_text", "src": text, "ru": ru,
                      "lang": lang})
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
        for own in self.last_spoken:
            if difflib.SequenceMatcher(None, norm(own), heard).ratio() >= 0.55:
                return True
        return False

    def transcribe_peer(self, pcm_bytes: bytes, sr: int = SR_ASR) -> tuple[str, str]:
        """Распознать чужую речь. Возвращает (текст, язык)."""
        import numpy as np
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if sr != SR_ASR:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(sr), SR_ASR)
            audio = resample_poly(audio, SR_ASR // g, int(sr) // g).astype(np.float32)
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 1e-4:
            audio = audio / peak * 0.7
        lang = None if self.peer_lang == "auto" else self.peer_lang
        segs, info = self.asr.transcribe(
            audio, language=lang, beam_size=1, vad_filter=False,
            condition_on_previous_text=False,
            no_speech_threshold=0.6, log_prob_threshold=-1.0)
        items = list(segs)
        if not items:
            return "", self.peer_lang
        speech = [s for s in items
                  if getattr(s, "no_speech_prob", 0.0) < 0.6
                  and getattr(s, "avg_logprob", -1.0) > -1.2]
        if not speech:
            return "", self.peer_lang
        text = " ".join(s.text.strip() for s in speech).strip()
        if not text or is_hallucination(text):
            return "", self.peer_lang
        detected = getattr(info, "language", None) or self.peer_lang
        if detected == "auto":
            detected = "es"
        return text, detected

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
        pcm = (np.clip(part, -1.0, 1.0) * 32767).astype(np.int16)
        emit({"event": "chunk", "seq": seq,
              "pcm": base64.b64encode(pcm.tobytes()).decode("ascii")})

    def _emit_incoming_chunk(self, part: np.ndarray, seq: int) -> None:
        """Отдать кусок входящего аудио в GUI (base64 int16, 24 кГц).

        Идёт в отдельный event incoming_chunk, чтобы GUI мог разделить
        исходящий перевод (в кабель) и входящий (в наушники).
        """
        pcm = (np.clip(part, -1.0, 1.0) * 32767).astype(np.int16)
        emit({"event": "incoming_chunk", "seq": seq,
              "pcm": base64.b64encode(pcm.tobytes()).decode("ascii")})

    def _synth_full(self, spoken: str, params: dict, seed: int) -> np.ndarray:
        """Синтезировать фразу целиком (numpy float32)."""
        try:
            import torch
            torch.manual_seed(seed)
        except Exception:
            pass
        chunks = self.tts.inference_stream(
            spoken, xtts_language(self.lang), self.gpt_latent, self.spk_emb,
            stream_chunk_size=STREAM_CHUNK, **params)
        parts = [c.detach().cpu().numpy() for c in chunks]
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts).astype(np.float32)

    def speak(self, text: str, seq: int = 0, ru: str = "") -> None:
        """Синтезировать испанский текст твоим голосом, отдавая чанки.

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
        self.last_spoken.append(spoken)
        del self.last_spoken[:-3]

        short = len(text.split()) <= 6

        if not short:
            # длинная фраза: потоком, без ожидания и без обработки
            try:
                import torch
                torch.manual_seed(1234)
                for c in self.tts.inference_stream(
                        spoken, xtts_language(self.lang), self.gpt_latent,
                        self.spk_emb, stream_chunk_size=STREAM_CHUNK, **params):
                    self._emit_chunk(c.detach().cpu().numpy(), seq)
            except Exception as exc:
                log(f"[engine] синтез не удался: {type(exc).__name__}: {exc}")
            emit({"event": "done", "seq": seq,
                  "ms": int((time.time() - t0) * 1000)})
            return

        # короткая фраза: синтезируем целиком, проверяем, обрабатываем
        audio = np.zeros(0, dtype=np.float32)
        for attempt in range(2):
            audio = self._synth_full(spoken, params, 1234 + attempt * 7919)
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
        emit({"event": "done", "seq": seq, "ms": int((time.time() - t0) * 1000)})

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
        # Запускаем синтез в отдельном потоке, чтобы не блокировать
        # главный цикл IPC и обработку исходящего перевода.
        threading.Thread(
            target=self._synthesize_incoming,
            args=(text, seq, voice_profile),
            daemon=True,
        ).start()

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
        # Запоминаем, что синтезируем — для защиты от аудиопетель
        self.last_spoken.append(text)
        del self.last_spoken[:-3]
        t0 = time.time()
        try:
            import torch
            torch.manual_seed(1234)
            with self.lock:
                for c in self.tts.inference_stream(
                        text, "ru", self.gpt_latent, self.spk_emb,
                        stream_chunk_size=STREAM_CHUNK,
                        temperature=0.75, top_p=0.88, top_k=60,
                        speed=1.02, repetition_penalty=5.0):
                    self._emit_incoming_chunk(c.detach().cpu().numpy(), seq)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] синтез входящего не удался: "
                f"{type(exc).__name__}: {exc}")
        emit({"event": "incoming_done", "seq": seq,
              "ms": int((time.time() - t0) * 1000)})


def main() -> None:
    global LOG_FILE

    engine = Engine()
    reference = ""
    for arg in sys.argv[1:]:
        if arg.startswith("--reference="):
            reference = arg.split("=", 1)[1]

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

    log(f"[engine] старт: reference={reference}")
    emit({"event": "boot"})

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
            elif cmd == "speak":
                engine.speak(msg.get("text", ""), msg.get("seq", 0))
            elif cmd == "lang":
                # язык перевода: es / en / ow (олдвест) / it
                code = engine.set_lang(msg.get("code", "es"))
                emit({"event": "lang", "code": code,
                      "title": _lang_info(code)["title"]})
            elif cmd == "peer_lang":
                # язык чужой речи: auto или конкретный
                code = engine.set_peer_lang(msg.get("code", "auto"))
                emit({"event": "peer_lang", "code": code})
            elif cmd == "peer":
                # фрагмент звука игры -> разбор речи игроков
                pcm = base64.b64decode(msg.get("pcm", ""))
                engine.push_peer_pcm(pcm, int(msg.get("sr", SR_ASR)))
            elif cmd == "liveliness":
                # уровень живости от пользователя (0 — ровно, 3 — максимум)
                engine.liveliness = max(0, min(3, int(msg.get("level", 2))))
                log(f"[engine] живость: {engine.liveliness}")
            elif cmd == "translate":
                # аудио -> текст RU -> текст ES -> озвучка
                pcm = base64.b64decode(msg.get("pcm", ""))
                sr = int(msg.get("sr", SR_ASR))
                floor = float(msg.get("floor", 0.0))
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
