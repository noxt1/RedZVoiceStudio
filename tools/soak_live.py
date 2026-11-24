"""Продолжительный прогон живого перевода: стабильность, очереди, память.

Сценарий циклически повторяет реальную работу приложения:
  * входящий канал — испанская/английская речь собеседника, с промежуточными
    срезами (partial) и финалом;
  * исходящий канал — русская речь пользователя -> перевод -> синтез;
  * периодически меняются режим (fast/quality/balanced), язык собеседника
    (es/en/auto) и перезапускается движок.

Пишет промежуточный прогресс в build/soak_progress.txt (чтобы можно было
следить за прогоном) и итог в build/soak.json.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
import time

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from live_client import LiveTranslator  # noqa: E402

WS = os.path.join(os.environ["LOCALAPPDATA"], "Auraloom", "workspace")
ENGINE_PY = os.path.join(os.environ["LOCALAPPDATA"], "Auraloom",
                         "engine", "Scripts", "python.exe")
SCRIPT = os.path.join(WS, "tools", "live_translate.py")
REF = os.path.join(WS, "reference.wav")
WAV_DIR = os.path.join(WS, "out", "wav")
ASSETS = os.path.join(ROOT, "build", "soak_assets")
PROGRESS = os.path.join(ROOT, "build", "soak_progress.txt")


def note(text: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {text}"
    print(line, flush=True)
    with open(PROGRESS, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def load_wav(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.float32), int(sr)


class Harness:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, float]] = []
        self.tr = LiveTranslator(ENGINE_PY, SCRIPT, REF,
                                 on_event=self._event, on_text=self._text)
        self.texts: list[dict] = []
        self.peer_lang = ""

    def _event(self, kind: str, data: dict) -> None:
        self.events.append((kind, data, time.time()))

    def _text(self, ru: str, es: str, tone: str = "") -> None:
        self.texts.append({"ru": ru, "es": es, "tone": tone,
                           "t": time.time()})

    def pump(self, seconds: float, until=None) -> bool:
        """Крутить poll() указанное время; until(event)->bool прерывает."""
        end = time.time() + seconds
        while time.time() < end:
            self.tr.poll()
            if until is not None:
                for kind, data, _ in self.events:
                    if until(kind, data):
                        return True
            time.sleep(0.02)
        return False

    def wait_ready(self, timeout: float = 240.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            self.tr.poll()
            if self.tr.ready:
                return True
            if self.tr.error:
                note(f"ОШИБКА движка: {self.tr.error}")
                return False
            time.sleep(0.05)
        return False

    def take(self) -> list[tuple[str, dict, float]]:
        out = self.events
        self.events = []
        return out

    def stats(self) -> dict | None:
        self.take()
        self.tr.send({"cmd": "stats"})
        end = time.time() + 8
        while time.time() < end:
            self.tr.poll()
            for kind, data, _ in self.events:
                if kind == "stats":
                    self.take()
                    return data
            time.sleep(0.02)
        return None


def make_ru_audio(h: Harness) -> tuple[np.ndarray, int]:
    """Синтезировать русскую фразу движком (XTTS ru) -> PCM 24 кГц."""
    os.makedirs(ASSETS, exist_ok=True)
    path = os.path.join(ASSETS, "ru_1.wav")
    if os.path.exists(path):
        return load_wav(path)
    h.take()
    h.tr.send({"cmd": "speak", "seq": 9001, "lang": "ru",
               "text": "Привет, как дела? Это проверка живого перевода."})
    parts: list[np.ndarray] = []
    end = time.time() + 180
    while time.time() < end:
        h.tr.poll()
        for kind, data, _ in h.take():
            if kind == "chunk" and int(data.get("seq", 0)) == 9001:
                raw = base64.b64decode(data.get("pcm", ""))
                parts.append(np.frombuffer(raw, dtype=np.int16))
            if kind == "done" and int(data.get("seq", 0)) == 9001:
                end = 0
        if not end:
            break
        time.sleep(0.02)
    if not parts:
        raise SystemExit("не удалось синтезировать русский образец")
    audio = np.concatenate(parts).astype(np.float32) / 32768.0
    sf.write(path, audio, 24000)
    note(f"русский образец: {len(audio) / 24000:.2f} с")
    return audio, 24000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "soak.json"))
    args = ap.parse_args()

    open(PROGRESS, "w", encoding="utf-8").close()
    ru_audio, ru_sr = (None, 24000)
    h = Harness()
    note("запуск движка")
    if not h.tr.start() or not h.wait_ready():
        note("движок не поднялся")
        return 2
    note("движок READY")
    try:
        ru_audio, ru_sr = make_ru_audio(h)
    except SystemExit as exc:
        note(str(exc))
        return 3
    # для исходящего канала движок ждёт 44.1 кГц float; ресемплим сами
    ru_44 = np.interp(
        np.linspace(0, len(ru_audio) - 1, int(len(ru_audio) * 44100 / ru_sr)),
        np.arange(len(ru_audio)), ru_audio).astype(np.float32)

    es_files = sorted(f for f in os.listdir(WAV_DIR)
                      if f.startswith("mx_") and f.endswith(".wav")
                      and not f.endswith(("_en.wav", "_it.wav", "_ow.wav")))
    en_files = sorted(f for f in os.listdir(WAV_DIR) if f.endswith("_en.wav"))
    note(f"фразы: es={len(es_files)} en={len(en_files)}")

    h.take()
    h.tr.set_lang("es")
    h.tr.set_src_lang("ru")
    h.tr.set_peer_lang("auto")
    h.tr.set_mode("balanced")
    h.pump(3)

    start_ts = time.time()
    deadline = start_ts + args.minutes * 60
    # для короткого прогона перезапуск делается в середине;
    # для длинного — каждые 20 минут
    if args.minutes * 60 < 2400:
        restart_due = [args.minutes * 60 * 0.55]
    else:
        restart_due = [1200.0 * (k + 1) for k in range(30)]
    scenes: list[dict] = []
    errors: list[dict] = []
    i = 0
    last_stats = 0.0
    mode_cycle = ["balanced", "fast", "quality", "balanced"]
    restarts: list[dict] = []

    def restart_engine() -> dict:
        note("перезапуск движка")
        h.tr.stop()
        h.pump(1)
        ok = h.tr.start() and h.wait_ready()
        if ok:
            h.tr.set_lang("es")
            h.tr.set_peer_lang("auto")
            h.tr.set_mode("balanced")
            h.pump(3)
        st = h.stats() or {}
        note(f"после перезапуска: ready={ok} stats={st}")
        return {"ok": bool(ok), "stats": st, "t": time.time()}

    while time.time() < deadline:
        i += 1
        # --- смена режима раз в 8 сцен ---
        if i % 8 == 0:
            mode = mode_cycle[(i // 8) % len(mode_cycle)]
            h.take()
            h.tr.set_mode(mode)
            h.pump(0.5)
            note(f"режим -> {mode}")
        # --- входящий канал ---
        use_en = i % 5 == 0
        files = en_files if use_en else es_files
        name = files[i % len(files)]
        # язык собеседника задаём явно под фразу; раз в 15 сцен — auto,
        # чтобы проверить автоопределение
        want_lang = "en" if use_en else "es"
        if i % 15 == 0:
            want_lang = "auto"   # проверка автоопределения
        if h.peer_lang != want_lang:
            h.take()
            h.tr.set_peer_lang(want_lang)
            h.peer_lang = want_lang
            h.pump(0.35)
            note(f"язык собеседника -> {want_lang}")
        audio, sr = load_wav(os.path.join(WAV_DIR, name))
        cut = int(len(audio) * 0.6)
        pcm_part = (np.clip(audio[:cut], -1, 1) * 32767).astype(np.int16).tobytes()
        pcm_full = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        h.take()
        h.texts = []
        t0 = time.time()
        h.tr.send_peer_pcm(pcm_part, sr, partial=True)
        h.tr.send_peer_pcm(pcm_full, sr, partial=False)
        # каждый 10-й раз исходящий перевод идёт ОДНОВРЕМЕННО с входящим
        want_out = (i % 2 == 0)
        concurrent = want_out and (i % 10 == 0)
        out_rec = None
        t_out = 0.0
        if concurrent:
            t_out = time.time()
            h.tr.translate_pcm(ru_44.copy(), 44100)
            out_rec = {"sent": True, "concurrent": True, "chunks": 0,
                       "first_ms": None, "done": False, "text": None}
        got = {"partials": 0, "final": None, "incoming_chunks": 0,
               "first_audio_ms": None, "metrics": None,
               "incoming_done": False, "partial_texts": [],
               "finals": 0, "peer_partial_seq": []}
        end = time.time() + 45
        while time.time() < end:
            h.tr.poll()
            for kind, data, _ in h.take():
                if kind == "peer_partial":
                    got["partials"] += 1
                    got["partial_texts"].append(data.get("text"))
                    got["peer_partial_seq"].append(data.get("seq"))
                elif kind == "peer_text":
                    got["finals"] += 1
                    got["final"] = {"src": data.get("src"),
                                    "ru": data.get("ru"),
                                    "lang": data.get("lang"),
                                    "asr_ms": data.get("asr_ms"),
                                    "mt_ms": data.get("mt_ms"),
                                    "total_ms": data.get("total_ms")}
                    got["final_ms"] = int((time.time() - t0) * 1000)
                    # приложение сразу заказывает озвучку перевода в наушники
                    if data.get("ru"):
                        h.tr.incoming_speak(data["ru"], seq=10000 + i)
                elif kind == "incoming_chunk":
                    if got["incoming_chunks"] == 0:
                        got["first_audio_ms"] = int((time.time() - t0) * 1000)
                    got["incoming_chunks"] += 1
                elif kind == "incoming_done":
                    got["incoming_done"] = True
                elif kind == "metrics":
                    got["metrics"] = data
                elif kind == "chunk" and concurrent:
                    if out_rec["chunks"] == 0:
                        out_rec["first_ms"] = int((time.time() - t_out) * 1000)
                    out_rec["chunks"] += 1
                elif kind == "done" and concurrent:
                    out_rec["done"] = True
                    out_rec["total_ms"] = int((time.time() - t_out) * 1000)
                elif kind == "error":
                    errors.append({"scene": i, "error": data, "t": time.time()})
                    note(f"ОШИБКА: {data.get('message')}")
                elif kind == "peer_lang_detected":
                    got["peer_lang"] = data.get("code")
            if got.get("incoming_done"):
                break
            time.sleep(0.02)
            if got.get("final") and not got["final"].get("ru"):
                break
            if got.get("final") and got["incoming_chunks"] and time.time() > t0 + 15:
                break

        # --- одновременный исходящий мог ещe не закончиться ---
        if concurrent and out_rec is not None and not out_rec["done"]:
            end = time.time() + 60
            while time.time() < end:
                h.tr.poll()
                for kind, data, _ in h.take():
                    if kind == "chunk":
                        if out_rec["chunks"] == 0:
                            out_rec["first_ms"] = int((time.time() - t_out) * 1000)
                        out_rec["chunks"] += 1
                    elif kind == "done":
                        out_rec["done"] = True
                        out_rec["total_ms"] = int((time.time() - t_out) * 1000)
                if out_rec["done"]:
                    break
                time.sleep(0.02)
            if h.texts:
                out_rec["text"] = h.texts[0]

        # --- исходящий канал (вторая сцена; при i%10 уже отправлен) ---
        out = out_rec
        if want_out and not concurrent:
            h.take()
            h.texts = []
            t_out = time.time()
            sent = h.tr.translate_pcm(ru_44.copy(), 44100)
            rec = {"sent": bool(sent), "chunks": 0, "first_ms": None,
                   "text": None, "done": False}
            end = time.time() + 60
            while time.time() < end:
                h.tr.poll()
                for kind, data, _ in h.take():
                    if kind == "chunk":
                        if rec["chunks"] == 0:
                            rec["first_ms"] = int((time.time() - t_out) * 1000)
                        rec["chunks"] += 1
                    elif kind == "done":
                        rec["done"] = True
                        rec["total_ms"] = int((time.time() - t_out) * 1000)
                    elif kind == "error":
                        errors.append({"scene": i, "where": "out",
                                       "error": data, "t": time.time()})
                if rec["done"]:
                    break
                time.sleep(0.02)
            if h.texts:
                rec["text"] = h.texts[0]
            out = rec

        scenes.append({
            "i": i, "file": name, "in": got, "out": out,
            "elapsed_s": round(time.time() - t0, 1),
        })

        # --- статистика раз в 60 с ---
        if time.time() - last_stats > 60:
            st = h.stats() or {}
            last_stats = time.time()
            note(f"stats: rss={st.get('rss_mb')} vram={st.get('vram_mb')} "
                 f"q={(st.get('queues') or {}).get('peer')} "
                 f"dropped={st.get('dropped')} "
                 f"cancelled={st.get('cancelled')}")
            scenes[-1]["stats"] = st

        # --- остановка и повторный запуск движка ---
        elapsed = time.time() - start_ts
        if len(restarts) < len(restart_due) and elapsed > restart_due[len(restarts)]:
            restarts.append(restart_engine())

        if i % 10 == 0:
            note(f"сцен: {i}, осталось {int((deadline - time.time()) / 60)} мин")

    final_stats = h.stats() or {}
    h.tr.stop()

    def pct(values, p):
        if not values:
            return None
        values = sorted(values)
        k = min(len(values) - 1, int(round((len(values) - 1) * p)))
        return values[k]

    asr = [s["in"]["final"]["asr_ms"] for s in scenes
           if s["in"].get("final") and s["in"]["final"].get("asr_ms")]
    mt = [s["in"]["final"]["mt_ms"] for s in scenes
          if s["in"].get("final") and s["in"]["final"].get("mt_ms")]
    first_in = [s["in"]["first_audio_ms"] for s in scenes
                if s["in"].get("first_audio_ms")]
    first_out = [s["out"]["first_ms"] for s in scenes
                 if s["out"] and s["out"].get("first_ms")]
    rss = [s["stats"].get("rss_mb") for s in scenes
           if s.get("stats") and s["stats"].get("rss_mb")]
    vram = [s["stats"].get("vram_mb") for s in scenes
            if s.get("stats") and s["stats"].get("vram_mb")]

    result = {
        "minutes": args.minutes,
        "scenes": len(scenes),
        "partials_total": sum(s["in"]["partials"] for s in scenes),
        "finals": sum(1 for s in scenes if s["in"].get("final")),
        "finals_with_ru": sum(1 for s in scenes
                              if s["in"].get("final") and s["in"]["final"].get("ru")),
        "empty_ru": sum(1 for s in scenes
                        if s["in"].get("final") and not s["in"]["final"].get("ru")),
        "outbound": {
            "concurrent": sum(1 for s in scenes
                              if s["out"] and s["out"].get("concurrent")),
            "sent": sum(1 for s in scenes if s["out"] and s["out"]["sent"]),
            "done": sum(1 for s in scenes if s["out"] and s["out"]["done"]),
            "with_text": sum(1 for s in scenes
                             if s["out"] and s["out"].get("text")),
        },
        "latency": {
            "asr_ms_p50": pct(asr, 0.5), "asr_ms_p95": pct(asr, 0.95),
            "asr_ms_max": max(asr) if asr else None,
            "mt_ms_p50": pct(mt, 0.5), "mt_ms_p95": pct(mt, 0.95),
            "first_in_p50": pct(first_in, 0.5), "first_in_p95": pct(first_in, 0.95),
            "first_in_max": max(first_in) if first_in else None,
            "first_out_p50": pct(first_out, 0.5),
            "first_out_p95": pct(first_out, 0.95),
            "first_out_max": max(first_out) if first_out else None,
        },
        "rss_mb": {"first": rss[0] if rss else None,
                   "last": rss[-1] if rss else None,
                   "min": min(rss) if rss else None,
                   "max": max(rss) if rss else None,
                   "median": statistics.median(rss) if rss else None},
        "vram_mb": {"min": min(vram) if vram else None,
                    "max": max(vram) if vram else None},
        "final_stats": final_stats,
        "restarts": restarts,
        "errors": errors,
        "scene_log": scenes,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    note(f"ГОТОВО: сцен={len(scenes)} ошибок={len(errors)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
