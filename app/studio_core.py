"""Ядро RedZ Voice Studio: запись, клонирование, проверки, раскладка.

Вся тяжёлая работа (torch/coqui-tts/whisper) выполняется отдельным процессом
движка, поэтому GUI не блокируется и в EXE не нужно тащить 4 ГБ torch.
"""

from __future__ import annotations

import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

import studio_paths as sp

SR = 44100


# --------------------------------------------------------------------------
# Запись
# --------------------------------------------------------------------------
def trim_by_energy(audio: np.ndarray, sr: int = SR, threshold_db: float = -38.0,
                   pad_ms: int = 60) -> np.ndarray:
    """Обрезать тишину по краям (порог считается от пика сигнала)."""
    if len(audio) == 0:
        return audio
    peak = float(np.abs(audio).max())
    if peak <= 1e-6:
        return audio
    thr = peak * (10.0 ** (threshold_db / 20.0))
    win = max(1, int(sr * 0.01))
    kernel = np.ones(win) / win
    smooth = np.convolve(np.abs(audio), kernel, mode="same")
    loud = np.flatnonzero(smooth > thr)
    if loud.size == 0:
        return audio
    pad = int(sr * pad_ms / 1000.0)
    return audio[max(0, loud[0] - pad): min(len(audio), loud[-1] + pad)]


def quality_report(audio: np.ndarray, sr: int = SR) -> dict:
    """Метрики качества записи."""
    if len(audio) == 0:
        return {"ok": False, "reason": "пусто"}
    dur = len(audio) / sr
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    clipped = int(np.sum(np.abs(audio) > 0.985))
    problems = []
    if dur < 1.0:
        problems.append(f"слишком коротко ({dur:.1f} c)")
    if dur > 30:
        problems.append(f"слишком долго ({dur:.1f} c)")
    if peak < 0.015:
        problems.append("тихо — подойди ближе или подними уровень микрофона")
    if peak > 0.99 and clipped > sr * 0.02:
        problems.append("захлёбывается — отойди от микрофона")
    if rms < 0.006:
        problems.append("мало речи — говори чётче или ближе")
    return {"ok": not problems, "dur": dur, "peak": peak, "rms": rms,
            "clipped": clipped, "reason": "; ".join(problems)}


class Recorder:
    """Живая запись с микрофона в память."""

    def __init__(self) -> None:
        self.buffer: list[np.ndarray] = []
        self.level = 0.0
        self.recording = False
        self._stream = None
        self.device = None
        self.sr = SR

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG001
        if status:
            return
        mono = indata[:, 0] if indata.ndim > 1 else indata
        self.buffer.append(mono.copy())
        self.level = float(np.abs(mono).max())

    def start(self, device=None) -> None:
        import sounddevice as sd
        from audiodev import best_rate
        self.buffer = []
        self.device = device
        # Частота — по устройству: на «чужих» частотах поток отдаёт тишину
        self.sr = best_rate(device, "input", SR)
        kwargs = {"device": device} if device is not None else {}
        self._stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                      callback=self._callback, blocksize=1024, **kwargs)
        self._stream.start()
        self.recording = True

    def stop(self) -> np.ndarray:
        import sounddevice as sd
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.recording = False
        if not self.buffer:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.buffer).astype("float32")


def _mic_memory_file() -> str:
    """Файл с запомненным микрофоном (тот, с которого шла последняя запись)."""
    return os.path.join(sp.workspace(), "last_mic.json")


def remember_mic(index: int | None, name: str) -> None:
    """Запомнить микрофон: мост и запись будут использовать его."""
    if index is None:
        return
    import json
    try:
        with open(_mic_memory_file(), "w", encoding="utf-8") as fh:
            json.dump({"index": int(index), "name": name}, fh, ensure_ascii=False)
    except Exception:
        pass


def recalled_mic() -> tuple[int | None, str]:
    """Запомненный микрофон (index, name) — если есть."""
    import json
    path = _mic_memory_file()
    if not os.path.exists(path):
        return None, ""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return int(data.get("index", -1)), data.get("name", "")
    except Exception:
        return None, ""


def pick_input_device() -> tuple[int | None, str]:
    """Выбрать микрофон: громче всех и без постоянного гула."""
    import sounddevice as sd
    try:
        devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        return None, f"не удалось опросить устройства: {exc}"
    candidates = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    if not candidates:
        return None, "нет устройств ввода"

    # Обобщённые драйверы («Первичный драйвер записи звука», «Стерео микшер»)
    # не являются реальными микрофонами — их лучше не использовать.
    generic = ("первичный драйвер", "primary sound capture", "стерео микшер",
               "stereo mix", "переназначение звуковых устр", "wave out",
               "what u hear")
    real = [(i, n) for i, n in candidates
            if not any(g in n.lower() for g in generic)]
    pool = real or candidates

    best, best_score, best_name = None, -1e9, ""
    for idx, name in pool:
        try:
            rec = sd.rec(int(0.9 * SR), samplerate=SR, channels=1, dtype="float32", device=idx)
            sd.wait()
            audio = rec.squeeze()
            if len(audio) == 0:
                continue
            peak = float(np.abs(audio).max())
            rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
            score = rms * min(peak / (rms + 1e-9), 6.0)
            if score > best_score:
                best, best_score, best_name = idx, score, name
        except Exception:
            continue
    if best is None:
        return None, "микрофон не отвечает"
    return best, best_name


def test_microphone(device=None) -> dict:
    """Записать 3 секунды и вернуть метрики — для проверки микрофона."""
    import sounddevice as sd
    kwargs = {"device": device} if device is not None else {}
    rec = sd.rec(int(3 * SR), samplerate=SR, channels=1, dtype="float32", **kwargs)
    sd.wait()
    audio = np.asarray(rec, dtype="float32").squeeze()
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean())) if audio.size else 0.0
    return {"peak": peak, "rms": rms,
            "verdict": "слышно, ок" if rms > 0.005 else "тишина — проверь устройство или уровень"}


# --------------------------------------------------------------------------
# Референс
# --------------------------------------------------------------------------
def estimate_snr(audio: np.ndarray, sr: int = SR) -> float:
    """Отношение сигнал/шум в дБ (по тихому «полу» vs активной речи)."""
    if len(audio) < sr // 4:
        return 0.0
    win = max(1, int(sr * 0.02))
    n = len(audio) // win
    if n < 4:
        return 0.0
    frames = audio[: n * win].reshape(n, win)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    floor = float(np.percentile(rms, 20))
    active = float(np.percentile(rms, 90))
    if floor <= 1e-9:
        return 60.0
    return float(20.0 * np.log10(max(active, 1e-9) / floor))


def build_reference(samples: list[str], out_path: str, max_seconds: float = 25.0) -> dict:
    """Собрать референс из записей.

    XTTS использует не больше ~30 c референса, поэтому берём лучшие записи
    (по «чистоте» и уровню) и обрезаем по длине. Записи упорядочиваются
    так, чтобы самые чистые попали в начало.
    """
    import soundfile as sf
    paths = [p for p in samples if os.path.exists(p)]
    if not paths:
        return {"ok": False, "reason": "нет записей"}

    scored = []
    for p in paths:
        audio, sr = sf.read(p, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        rep = quality_report(audio)
        snr = estimate_snr(audio)
        # приоритет: пригодность -> чистота -> уровень
        rank = (1 if rep["ok"] else 0, snr, rep["rms"])
        scored.append((rank, p, audio, snr))
    scored.sort(key=lambda t: t[0], reverse=True)

    parts: list[np.ndarray] = []
    total = 0.0
    used = 0
    for _, _, audio, _ in scored:
        dur = len(audio) / SR
        if total + dur > max_seconds and parts:
            break
        parts.append(audio)
        parts.append(np.zeros(int(SR * 0.35), dtype="float32"))
        total += dur
        used += 1

    if not parts:
        return {"ok": False, "reason": "нет пригодных записей"}

    ref = np.concatenate(parts)
    ref = trim_by_energy(ref)
    peak = float(np.abs(ref).max())
    if peak > 0:
        ref = ref / peak * 0.95
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, ref, SR, subtype="PCM_16")
    return {"ok": True, "path": out_path, "duration": len(ref) / SR, "count": used,
            "snr": round(scored[0][3], 1)}


# --------------------------------------------------------------------------
# Запуск задач движком
# --------------------------------------------------------------------------
_active_proc = None


def cancel_job() -> bool:
    """Прервать текущую задачу движка."""
    global _active_proc
    if _active_proc is None:
        return False
    try:
        _active_proc.kill()
        return True
    except Exception:
        return False


def run_engine(args: list[str], on_line=None, cwd: str | None = None) -> int:
    """Запустить скрипт движком, транслируя вывод в колбэк."""
    global _active_proc
    python = sp.engine_python()
    if not python:
        return -1
    # Движок печатает испанский текст («¡», «é», «ó»). Если у него stdout
    # в cp1251 (обычная кодировка Windows по умолчанию), печать падает с
    # UnicodeEncodeError и задача умирает на первой фразе с акцентом.
    # Поэтому кодировку дочернего процесса задаём ЯВНО.
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [python, *args], cwd=cwd or sp.workspace(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        env=env,
    )
    _active_proc = proc
    try:
        for line in proc.stdout:
            if on_line:
                on_line(line.rstrip())
    finally:
        _active_proc = None
    return proc.wait()


def tools_dir() -> str:
    return sp.workspace_tools()


def clone_all(reference: str, attempts: int = 10, on_line=None) -> int:
    """Переозвучить все реплики своим голосом (XTTS)."""
    script = os.path.join(tools_dir(), "xtts_clone.py")
    if not os.path.exists(script):
        if on_line:
            on_line("Нет xtts_clone.py — нужен исходники проекта рядом с EXE")
        return -1
    return run_engine([script, "--reference", reference, "--attempts", str(attempts),
                        "--out", sp.output_paths()["out_wav"].rsplit(os.sep, 1)[0]],
                       on_line=on_line)


def piper_all(lines_path: str | None = None, on_line=None) -> int:
    """Озвучить офлайн-голосом Piper es-MX."""
    script = os.path.join(tools_dir(), "synthesize.py")
    if not os.path.exists(script):
        if on_line:
            on_line("Нет synthesize.py — нужен исходники проекта рядом с EXE")
        return -1
    return run_engine([script, "--engine", "piper", "--tries", "6",
                        "--out", sp.output_paths()["out_wav"].rsplit(os.sep, 1)[0]],
                       on_line=on_line)


def verify_similarity(reference: str, on_line=None) -> int:
    script = os.path.join(tools_dir(), "voice_similarity.py")
    if not os.path.exists(script):
        return -1
    return run_engine([script, "--reference", reference,
                        "--wav-dir", sp.output_paths()["out_wav"]], on_line=on_line)


def verify_quality(on_line=None) -> int:
    script = os.path.join(tools_dir(), "check_quality.py")
    if not os.path.exists(script):
        return -1
    return run_engine([script], on_line=on_line)


def verify_rules(on_line=None) -> int:
    script = os.path.join(tools_dir(), "check_rules.py")
    if not os.path.exists(script):
        return -1
    return run_engine([script], on_line=on_line)


def verify_sync(on_line=None) -> int:
    script = os.path.join(tools_dir(), "check_sync.py")
    if not os.path.exists(script):
        return -1
    return run_engine([script], on_line=on_line)


def write_report(title: str, done_ids: list[str], total_ids: list[str],
                 seconds: float, reason: str) -> str:
    r"""Отчёт о прерванной/завершённой задаче -> workspace\logs."""
    import datetime
    logs = os.path.join(sp.workspace(), "logs")
    os.makedirs(logs, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(logs, f"report_{stamp}.txt")

    done_set = set(done_ids)
    missing = [i for i in total_ids if i not in done_set]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"Задача: {title}\n")
        fh.write(f"Итог: {reason}\n")
        fh.write(f"Длительность: {seconds:.1f} с\n")
        fh.write(f"Готово: {len(done_set)} из {len(total_ids)}\n")
        if missing:
            fh.write("Не озвучено: " + ", ".join(missing) + "\n")
        fh.write(f"Отчёт сохранён: {path}\n")
    return path


def distribute() -> dict:
    """Разложить озвучку: ogg -> sounds/ (ресурс), mp3 -> player/mp3/."""
    p = sp.output_paths()
    moved = {"ogg": 0, "mp3": 0, "failed": 0}
    for src, dst, key in ((p["out_ogg"], p["sounds"], "ogg"),
                           (p["out_mp3"], p["player_mp3"], "mp3")):
        os.makedirs(dst, exist_ok=True)
        for f in glob.glob(os.path.join(src, "mx_*." + key)):
            # copy2 падает с PermissionError, если файл занят
            # (антивирус, проигрыватель, второй экземпляр приложения)
            if not sp._safe_copy(f, os.path.join(dst, os.path.basename(f))):
                moved["failed"] += 1
                continue
            moved[key] += 1
    return moved


# Подсказки для записи образца голоса
PROMPTS_RU = [
    "Привет, меня зовут {name}. Сегодня спокойный день, ничего особенного.",
    "Как круто, всё отлично! У меня тут всё хорошо.",
    "Не фигня, брат, давай работать. Пойдём, пора.",
    "Ну всё, почти закончили, осталось немного.",
    "Точно, здесь всё круто, всё хорошо.",
    "Чё за фигня? Вот мои деньги, держи.",
    "Не смейся надо мной, серьёзно, работаем.",
    "Уже круто, я иду, не переживай, всё будет хорошо.",
    "Ты мой друг, я тебя очень люблю, вот так.",
    "Уже не говори со мной, пожалуйста, спасибо тебе.",
    "Подъём, все тут, слушайте внимательно, начинаем.",
    "Вниз, сойди оттуда, прямо сейчас, быстро.",
    "Не двигайся, руки вверх, оружие брось на пол.",
    "Сначала стреляй, я сдаюсь, больше не могу, всё.",
    "Помогите, спасите, у меня пуля в ноге, быстрее!",
    "Принимаю свою судьбу, не принимаю, точка, мне нравится.",
    "Вот твои деньги, не ной, иди к другому, твоя очередь.",
    "Уже хочу есть, кофе с молоком, пожалуйста, спасибо.",
]

PROMPTS_ES = [
    "Hola, me llamo {name}. Hoy es un dia tranquilo.",
    "Que chido, guay! Todo bien por aqui.",
    "No manches, carnal, vamos a trabajar.",
    "A huevo, ya casi terminamos.",
    "Neta que no manches, todo chido aqui.",
    "Que pedo, guay? Ahi esta mi dinero.",
    "Pinche cabron, no te burles de mi.",
    "Ya esta chido, aqui voy, no te preocupes.",
    "Chilango de mi corazon, te quiero mucho.",
    "Ya ni me hable, por favor, gracias.",
    "Arriba, todos aqui, listen bien.",
    "Abajo, bajese de ahi, ahora.",
    "No se mueva, manos arriba, suelte el arma.",
    "Dispara primero, me rindo, ya no puedo mas.",
    "Auxilio, socorro por favor, tengo un balazo en la pierna.",
    "Acepto mi destino, no acepto, punto, me late.",
    "Aqui esta tu dinero, no te lo lopinees, vete pal otro.",
    "Ya me dio hambre, cafe con leche, por favor.",
]


def export_server_resource() -> str:
    """Собрать папку ресурса для установки на сервер RedZ/FiveM.

    Копирует fxmanifest.lua, client.lua, keybinds.lua, server.lua, config.lua,
    html/ и sounds/ (ogg). Всё, что нужно, чтобы фразы играл сервер и их
    слышали все — без виртуального кабеля и без подмешивания в микрофон.
    """
    src_root = sp.resource_dir()
    dst_root = os.path.join(sp.workspace(), "server_resource")
    os.makedirs(dst_root, exist_ok=True)

    for fname in ("fxmanifest.lua", "client.lua", "keybinds.lua", "server.lua",
                  "config.lua"):
        src = os.path.join(src_root, fname)
        if os.path.exists(src):
            sp._safe_copy(src, os.path.join(dst_root, fname))

    html_src = os.path.join(src_root, "html")
    html_dst = os.path.join(dst_root, "html")
    if os.path.isdir(html_src):
        os.makedirs(html_dst, exist_ok=True)
        sp._safe_copy(os.path.join(html_src, "index.html"),
                      os.path.join(html_dst, "index.html"))

    sounds_src = sp.output_paths()["sounds"]
    sounds_dst = os.path.join(dst_root, "sounds")
    os.makedirs(sounds_dst, exist_ok=True)
    count = 0
    for path in glob.glob(os.path.join(sounds_src, "mx_*.ogg")):
        if not sp._safe_copy(path, os.path.join(sounds_dst, os.path.basename(path))):
            continue
        count += 1

    return dst_root


def load_lines() -> list[dict]:
    path = sp.output_paths()["lines"]
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["lines"]


# --------------------------------------------------------------------------
# Языки (общий модуль tools/voice_lang.py с движком и приложением)
# --------------------------------------------------------------------------
_LANG_MODULE = None


def lang_module():
    """Загрузить модуль языков (tools/voice_lang.py).

    Модуль один и тот же для движка и приложения: в нём коды языков XTTS,
    модели перевода и переписывание текста в стиле вестерна.
    """
    global _LANG_MODULE
    if _LANG_MODULE is not None:
        return _LANG_MODULE
    import importlib.util
    import sys as _sys
    mod = None
    path = sp.tool_path("voice_lang.py")
    if path and os.path.exists(path):
        # Добавляем папку tools в sys.path, чтобы voice_lang.py мог
        # импортировать western_style (и другие модули из tools/).
        tools_dir = os.path.dirname(path)
        if tools_dir not in _sys.path:
            _sys.path.insert(0, tools_dir)
        try:
            spec = importlib.util.spec_from_file_location("voice_lang", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:  # noqa: BLE001
            print(f"[core] не удалось загрузить voice_lang: {exc}")
            mod = None
    if mod is None:
        # запасной вариант: только испанский
        class _Fallback:
            LANGS = {"es": {"title": "Испанский", "xtts": "es",
                            "mt": ["Helsinki-NLP/opus-mt-ru-es"],
                            "field": "es", "suffix": ""}}
            DEFAULT_LANG = "es"
            LANG_ORDER = ("es",)

            @staticmethod
            def titles():
                return [("es", "Испанский")]

            @staticmethod
            def suffix(code):
                return ""

            @staticmethod
            def field(code):
                return "es"

            @staticmethod
            def title(code):
                return "Испанский"

            @staticmethod
            def phrase_name(phrase_id, code):
                return f"mx_{phrase_id}"

            @staticmethod
            def to_oldwest(text):
                return text
        mod = _Fallback()
    _LANG_MODULE = mod
    return mod


def lang_titles() -> list[tuple[str, str]]:
    """Список языков (код, название) для выбора в интерфейсе."""
    return lang_module().titles()


def lang_suffix(code: str) -> str:
    """Суффикс файла озвучки для языка ('' у испанского)."""
    return lang_module().suffix(code)


def lang_title(code: str) -> str:
    """Название языка."""
    return lang_module().title(code)


def to_oldwest(text: str) -> str:
    """Переписать английский текст в стиле вестерна."""
    try:
        return lang_module().to_oldwest(text)
    except Exception:
        return text


# --------------------------------------------------------------------------
# Озвучка
# --------------------------------------------------------------------------
def _out_root() -> str:
    return os.path.dirname(sp.output_paths()["out_wav"])


def clone_one(text: str, reference: str, phrase_id: str, on_line=None,
              expressiveness: int = 2, lang: str = "es") -> int:
    """Озвучить одну свою фразу своим голосом -> out/mx_<id>.*"""
    script = os.path.join(tools_dir(), "xtts_clone.py")
    if not os.path.exists(script):
        if on_line:
            on_line("Нет xtts_clone.py")
        return -1
    return run_engine([script, "--reference", reference, "--text", text,
                        "--id", phrase_id, "--expressiveness", str(expressiveness),
                        "--lang", lang,
                        "--out", _out_root()], on_line=on_line)


def clone_all(reference: str, attempts: int = 10, on_line=None, texts=None,
              expressiveness: int = 2, lang: str = "es") -> int:
    """Переозвучить все фразы своим голосом (XTTS).

    texts — полный список приложения: [{'id': '01', 'text': '...'}].
    Если список не передан, берутся фразы из lines.json.

    Список передаётся ФАЙЛОМ: JSON с кириллицей в аргументах командной
    строки ломается (аргумент обрезается, argparse его не разбирает) —
    из-за этого озвучивалась лишь часть фраз.

    lang — язык озвучки (es, en, ow, it). Для не-испанского файлы
    получают суффикс: mx_01_en.mp3 (испанский остаётся mx_01.mp3).
    """
    script = os.path.join(tools_dir(), "xtts_clone.py")
    if not os.path.exists(script):
        if on_line:
            on_line("Нет xtts_clone.py — нужен исходники проекта рядом с EXE")
        return -1
    args = [script, "--reference", reference, "--attempts", str(attempts),
            "--expressiveness", str(expressiveness),
            "--lang", lang,
            "--out", _out_root()]
    if texts:
        # Файл со списком — ИМЕННО УНИКАЛЬНЫЙ на каждый запуск.
        # Общий файл ломался, когда приложение было открыто дважды
        # (второй экземпляр перезаписывал файл, и первый падал с
        # PermissionError при чтении).
        payload_path = os.path.join(
            sp.workspace(),
            f"phrases_payload_{os.getpid()}_{int(time.time() * 1000) % 100000}.json")
        with open(payload_path, "w", encoding="utf-8") as fh:
            json.dump(texts, fh, ensure_ascii=False)
        args += ["--texts-file", payload_path]
    try:
        code = run_engine(args, on_line=on_line)
    finally:
        # временные payload-файлы не копятся
        try:
            if "payload_path" in dir() and os.path.exists(payload_path):
                os.remove(payload_path)
        except Exception:
            pass
    return code
