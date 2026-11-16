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
ASR_MODEL = os.environ.get("REDZ_ASR_MODEL", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
ASR_FALLBACK = os.environ.get("REDZ_ASR_FALLBACK", "Systran/faster-whisper-small")

# Точность вычислений для распознавания:
#   float16      — VRAM 2241 МБ
#   int8_float16 — тот же текст на записях пользователя, VRAM 1019 МБ
#                  (минус ~1.2 ГБ — важно, когда параллельно игра)
# Замер: research/bench_optimization.py, research/bench_int8_quality.py
ASR_COMPUTE = os.environ.get("REDZ_ASR_COMPUTE", "int8_float16")

# Минимальная уверенность определения языка собеседника (режим auto).
# Ниже порога фраза не переводится: лучше пропустить, чем озвучить не то.
PEER_LANG_MIN_CONF = float(os.environ.get("REDZ_PEER_LANG_CONF", "0.60"))


def _hf_hub_dir() -> str:
    """Каталог кэша HuggingFace (оттуда движок берёт модели)."""
    return os.environ.get("HF_HUB_CACHE") or os.path.expanduser(
        os.path.join("~", ".cache", "huggingface", "hub"))


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
MT_DEVICE = os.environ.get("REDZ_MT_DEVICE", "cpu")

# Размер чанка XTTS: чем меньше, тем раньше появляется первый звук.
# Важно, когда GPU занят игрой.
#
# Правка Этап C.7.2: было 10 — XTTS выдавал фразы «обрывками»: на стыке
# чанков пропадали слоги, слова не договаривались. 30 даёт связную речь
# с приемлемой задержкой (первый звук ~на 200 мс позже, чем при 10).
STREAM_CHUNK = int(os.environ.get("REDZ_STREAM_CHUNK", "30"))

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
        # Имя загруженной модели распознавания (для выбора в интерфейсе).
        self.asr_model = ""
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
        # Язык перевода: es (по умолчанию), en, ow (олдвест), it, mg (мегрельский)
        self.lang = "es"
        # Язык, на котором говорит пользователь (источник исходящего перевода).
        # Сейчас надёжно поддержан только русский: MT-веса ru->X уже есть, а
        # X->ru требует отдельной модели (появится после установки пакета).
        self.src_lang = "ru"
        # Кэш моделей перевода: код -> (токенизатор, модель).
        # Держим не больше двух (текущий + испанский), чтобы не съедать RAM.
        self._mt_cache: dict[str, list] = {}
        # Piper-озвучка для языков, которых нет в XTTS (например, грузинский).
        # Кэш: путь к .onnx -> PiperVoice
        self._piper_cache: dict[str, object] = {}
        # ---------- перехват речи других игроков ----------
        self._peer_q: "queue.Queue" = queue.Queue(maxsize=8)
        self._peer_thread: threading.Thread | None = None
        # Язык чужой речи: "auto" (определяем сами) или es/en/it/ru
        self.peer_lang = "auto"
        # Автоскачивание недостающих пакетов перевода — ВЫКЛЮЧЕНО по умолчанию.
        # Включается только пользователем в настройках приложения.
        self.auto_download = False
        self._downloaded: set[str] = set()
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
                self.asr_model = name
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

    def set_asr(self, name: str) -> str:
        """Переключить модель распознавания (только уже установленную)."""
        name = (name or "").strip()
        if not name or name == self.asr_model:
            return self.asr_model
        if not _model_installed(name):
            raise RuntimeError(f"модель не установлена: {name}")
        from faster_whisper import WhisperModel
        log(f"[engine] смена ASR: {self.asr_model} -> {name}")
        t0 = time.time()
        new = WhisperModel(name, device="cuda", compute_type=ASR_COMPUTE)
        old = self.asr
        self.asr = new
        self.asr_model = name
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

    def download_package(self, src: str) -> bool:
        """Скачать веса перевода src->ru (только по настройке пользователя)."""
        names = [_chain_name(i) for i in _reverse_mt_names(src)]
        if not names:
            return False
        pair = f"{src}->ru"
        emit({"event": "package", "pair": pair, "state": "downloading",
              "models": names})
        log(f"[engine] скачивание пакета {pair}: {names}")
        try:
            from huggingface_hub import snapshot_download
            for name in names:
                snapshot_download(name)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] пакет {pair} не скачался: {exc}")
            emit({"event": "package", "pair": pair, "state": "error",
                  "message": f"{type(exc).__name__}: {exc}"})
            return False
        ok = self.reverse_available(src)
        self._downloaded.add(pair)
        log(f"[engine] пакет {pair}: {'установлен' if ok else 'файлы не найдены'}")
        emit({"event": "package", "pair": pair,
              "state": "installed" if ok else "error"})
        return ok

    def reverse_available(self, src: str) -> bool:
        """Есть ли чем перевести чужую речь на русский (модели на диске)."""
        if src in ("", "auto", "ru"):
            return True
        chain = _reverse_mt_names(src)
        if chain and all(_model_installed(_chain_name(i)) for i in chain):
            return True
        # запасной путь: Whisper -> английский, затем en->ru
        fb = _reverse_mt_names("en")
        return bool(fb) and all(_model_installed(_chain_name(i)) for i in fb)

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
        if code not in self._mt_cache:
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
                    name, dtype=dtype, low_cpu_mem_usage=True).to(MT_DEVICE).eval()
            except Exception:
                # не все CPU поддерживают fp16-матмулы — откатываемся
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    name, dtype=torch.float32,
                    low_cpu_mem_usage=True).to(MT_DEVICE).eval()
            if target:
                chain.append((tok, model, target))
            else:
                chain.append((tok, model))
        # Кэш: не больше двух языков (текущий + испанский) — RAM конечен.
        if len(self._mt_cache) >= 2 and key not in self._mt_cache:
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
        # кэш голоса: считается один раз (1.4 с), дальше 0.03 с
        self.gpt_latent, self.spk_emb = self.tts.get_conditioning_latents(
            audio_path=[reference])
        log(f"[engine] XTTS + кэш голоса за {(time.time() - t0) * 1000:.0f} мс, "
            f"RSS={_rss_mb():.0f} МБ")

    # ---------- перевод текста ----------
    def _run_chain(self, text: str, chain: list[tuple]) -> str:
        """Прогнать текст по цепочке моделей перевода.

        Элемент цепочки — пара (токенизатор, модель) либо
        (токенизатор, модель, target_токен). Target-токен нужен для
        мультиязычных моделей (opus-mt-en-mul): >>kat<< = грузинский.
        """
        import torch
        for item in chain:
            tok, model = item[0], item[1]
            target = item[2] if len(item) > 2 else None
            batch = tok([text], return_tensors="pt", padding=True).to(MT_DEVICE)
            gen_kwargs = {}
            if target:
                try:
                    tid = tok.convert_tokens_to_ids(target)
                    if tid is not None and tid != tok.unk_token_id:
                        gen_kwargs["forced_bos_token_id"] = tid
                except Exception:
                    pass
            with torch.inference_mode():
                out = model.generate(**batch, max_new_tokens=128, num_beams=1,
                                     **gen_kwargs)
            text = tok.batch_decode(out, skip_special_tokens=True)[0].strip()
            # Мультиязычная модель оставляет префикс цели — убираем
            if target and text.startswith(target.strip(">")):
                text = text.split(None, 1)[1] if " " in text else ""
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
        """Перевести чужую речь на русский (перехват игроков).

        Если для языка есть прямая модель (es/en/it) — используем её.
        Иначе — запасной путь через английский (см. _translate_via_english),
        который требует исходного аудио: Whisper сам переводит речь
        на английский (task="translate"), дальше eng->ru одной моделью.
        """
        if not text.strip() or src == "ru":
            return text
        chain = self._mt_reverse(src)
        if not chain:
            return ""
        try:
            return self._run_chain(text, chain)
        except Exception as exc:  # noqa: BLE001
            log(f"[engine] перевод {src}->ru не удался: "
                f"{type(exc).__name__}: {exc}")
            return ""

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
            return self._run_chain(en, chain)
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
                audio, task="translate", beam_size=1, vad_filter=False,
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
            audio, language=self.src_lang, beam_size=1, vad_filter=False,
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
                if not self.reverse_available(lang):
                    # Если пользователь разрешил автоскачивание — скачиваем
                    # пакет и продолжаем с ЭТОЙ ЖЕ фразой (не теряем её).
                    if self.auto_download and self.download_package(lang):
                        log(f"[engine] пакет {lang}->ru готов, продолжаю фразу")
                    else:
                        # Не подменяем перевод английским текстом: лучше явно
                        # сказать, что для направления нет модели.
                        log(f"[engine] перехват {lang}->ru: нет модели перевода")
                        emit({"event": "peer_text", "src": text, "ru": "",
                              "lang": lang, "missing_mt": f"{lang}->ru"})
                        continue
                ru = self._translate_peer_to_ru(text, lang, pcm, sr)
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
        prob = float(getattr(info, "language_probability", 0.0) or 0.0)
        if self.peer_lang == "auto":
            log(f"[engine] язык собеседника: {detected}, "
                f"уверенность {prob:.2f}")
            # Одно короткое слово легко «опознать» неверно (испанская фраза
            # на 3 с ушла в японский). При низкой уверенности фразу не
            # переводим, а ждём следующую или ручного выбора.
            if prob < PEER_LANG_MIN_CONF:
                log(f"[engine] уверенность ниже {PEER_LANG_MIN_CONF:.2f} — "
                    f"язык не применяю, фразу пропускаю")
                return "", self.peer_lang
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
            stream_chunk_size=STREAM_CHUNK, overlap_wav_len=2048, **params)
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

    def speak(self, text: str, seq: int = 0, ru: str = "") -> None:
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
                # Вариативный seed: фиксированный 1234 давал монотонность.
                self._seed_counter = getattr(self, "_seed_counter", 0) + 1
                seed = (abs(hash(spoken)) % 100000) + self._seed_counter * 7919
                torch.manual_seed(seed)
                for c in self.tts.inference_stream(
                        spoken, xtts_language(self.lang), self.gpt_latent,
                        self.spk_emb, stream_chunk_size=STREAM_CHUNK,
                        overlap_wav_len=2048, **params):
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
            # ВАРИАТИВНЫЙ seed: с фиксированным 1234 каждая фраза звучала
            # одинаково монотонно («неживо»). Берём seed от хэша текста и
            # счётчика — одинаковые фразы не повторяются точь-в-точь.
            self._seed_counter = getattr(self, "_seed_counter", 0) + 1
            seed = (abs(hash(text)) % 100000) + self._seed_counter * 7919
            torch.manual_seed(seed)
            # Параметры для живости: чуть выше temperature (0.78) даёт
            # интонационное разнообразие, но не «кашу» (потолок 0.82).
            with self.lock:
                for c in self.tts.inference_stream(
                        text, "ru", self.gpt_latent, self.spk_emb,
                        stream_chunk_size=STREAM_CHUNK,
                        temperature=0.78, top_p=0.87, top_k=52,
                        speed=0.97, repetition_penalty=10.0,
                        overlap_wav_len=2048):
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
            elif cmd == "set_asr":
                # переключение модели распознавания (только установленной)
                name = engine.set_asr(msg.get("name", ""))
                emit({"event": "asr", "name": name})
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
