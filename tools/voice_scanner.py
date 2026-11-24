"""Сканер голоса — интерактивный инструмент для клонирования.

Нажимаешь кнопку, читаешь подсказки по-испански, он записывает,
затем собирает образец голоса и переозвучивает все реплики панели ТВОИМ голосом.

Запуск:
    python tools\\voice_scanner.py

Что внутри:
  * GUI (tkinter): кнопка «Записать», список подсказок, индикатор уровня
  * автоматическая обрезка тишины по энергии сигнала
  * проверка качества каждой записи (длительность, пики, уровень)
  * сборка референса из лучших записей
  * клонирование через XTTS-v2 + авто-починка
  * оценка похожести через спикер-энкодер XTTS (cosine similarity)
"""

from __future__ import annotations

import glob
import json
import os
import queue
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.environ.setdefault("COQUI_TOS_AGREED", "1")

SR = 44100

# Подсказки для чтения. Русский вариант — для тех, кто говорит по-русски;
# испанский даёт более точное мексиканское произношение при клонировании.
PROMPTS_ES = [
    ("Hola, me llamo {name}. Hoy es un dia tranquilo.", "Привет, меня зовут {name}. Сегодня спокойный день."),
    ("Que chido, guay! Todo bien por aqui.", "Как круто! У меня тут всё хорошо."),
    ("No manches, carnal, vamos a trabajar.", "Не фигня, брат, пойдём работать."),
    ("A huevo, ya casi terminamos.", "В яйца, мы почти закончили."),
    ("Neta que no manches, todo chido aqui.", "Точно, всё круто тут."),
    ("Que pedo, guay? Ahi esta mi dinero.", "Чё за фигня? Вот мои деньги."),
    ("Pinche cabron, no te burles de mi.", "Пинче каброн, не смейся надо мной."),
    ("Ya esta chido, aqui voy, no te preocupes.", "Уже круто, я иду, не волнуйся."),
    ("Chilango de mi corazon, te quiero mucho.", "Чиланго моего сердца, я тебя очень люблю."),
    ("Ya ni me hable, por favor, gracias.", "Уже не говори со мной, пожалуйста, спасибо."),
    ("Arriba, todos aqui, listen bien.", "Подъём, все тут, слушайте внимательно."),
    ("Abajo, bajese de ahi, ahora.", "Вниз, слезай оттуда, сейчас."),
    ("No se mueva, manos arriba, suelte el arma.", "Не двигайся, руки вверх, брось оружие."),
    ("Dispara primero, me rindo, ya no puedo mas.", "Сначала стреляй, сдаюсь, больше не могу."),
    ("Auxilio, socorro por favor, tengo un balazo en la pierna.", "Помогите, спасите, у меня пуля в ноге."),
    ("Acepto mi destino, no acepto, punto, me late.", "Принимаю свою судьбу, не принимаю, точка, мне нравится."),
    ("Aqui esta tu dinero, no te lo lopinees, vete pal otro.", "Вот твои деньги, не ной, иди к другому."),
    ("Ya me dio hambre, cafe con leche, por favor.", "Уже хочу есть, кофе с молоком, пожалуйста."),
]

# Тот же набор по-русски: XTTS клонирует тембр из любого языка и потом
# говорит по-испански, поэтому референс на русском тоже работает.
PROMPTS_RU = [
    ("Привет, меня зовут {name}. Сегодня спокойный день, ничего особенного.", None),
    ("Как круто, всё отлично! У меня тут всё хорошо.", None),
    ("Не фигня, брат, давай работать. Пойдём, пора.", None),
    ("Ну всё, почти закончили, осталось немного.", None),
    ("Точно, здесь всё круто, всё хорошо.", None),
    ("Чё за фигня? Вот мои деньги, держи.", None),
    ("Не смейся надо мной, серьёзно, работаем.", None),
    ("Уже круто, я иду, не переживай, всё будет хорошо.", None),
    ("Ты мой друг, я тебя очень люблю, вот так.", None),
    ("Уже не говори со мной, пожалуйста, спасибо тебе.", None),
    ("Подъём, все тут, слушайте внимательно, начинаем.", None),
    ("Вниз, сойди оттуда, прямо сейчас, быстро.", None),
    ("Не двигайся, руки вверх, оружие брось на пол.", None),
    ("Сначала стреляй, я сдаюсь, больше не могу, всё.", None),
    ("Помогите, спасите, у меня пуля в ноге, быстрее!", None),
    ("Принимаю свою судьбу, не принимаю, точка, мне нравится.", None),
    ("Вот твои деньги, не ной, иди к другому, твоя очередь.", None),
    ("Уже хочу есть, кофе с молоком, пожалуйста, спасибо.", None),
]

LANG = "ru"  # язык подсказок: "ru" или "es"


def prompts_for(lang: str) -> list[tuple[str, str | None]]:
    return PROMPTS_RU if lang == "ru" else PROMPTS_ES


PROMPTS = prompts_for(LANG)


def set_lang(lang: str) -> None:
    """Сменить язык подсказок (ru / es)."""
    global LANG, PROMPTS
    LANG = lang
    PROMPTS = prompts_for(lang)


def load_lines() -> list[dict]:
    with open(os.path.join(ROOT, "lines.json"), encoding="utf-8") as fh:
        return json.load(fh)["lines"]


# --------------------------------------------------------------------------
# Работа со звуком
# --------------------------------------------------------------------------
def trim_by_energy(audio: np.ndarray, sr: int = SR,
                   threshold_db: float = -38.0, pad_ms: int = 60) -> np.ndarray:
    """Обрезать тишину по краям: порог считается от пика сигнала."""
    if len(audio) == 0:
        return audio
    peak = float(np.abs(audio).max())
    if peak <= 1e-6:
        return audio
    thr = peak * (10.0 ** (threshold_db / 20.0))
    # скользящее среднее, чтобы не реагировать на одиночные щелчки
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
    if dur < 1.2:
        problems.append(f"слишком коротко ({dur:.1f} c)")
    if dur > 25:
        problems.append(f"слишком долго ({dur:.1f} c)")
    if peak < 0.02:
        problems.append("тихо — подойди ближе к микрофону")
    if peak > 0.99 and clipped > sr * 0.02:
        problems.append("захлёбывается — отойди от микрофона")
    if rms < 0.01:
        problems.append("мало речи — говори чётче")
    return {
        "ok": not problems,
        "dur": dur,
        "peak": peak,
        "rms": rms,
        "clipped": clipped,
        "reason": "; ".join(problems),
    }


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
def run_gui() -> str:
    """Запускает окно записи. Возвращает путь к собранному референсу."""
    import tkinter as tk
    from tkinter import ttk
    import soundfile as sf
    import sounddevice as sd

    samples_dir = os.path.join(ROOT, "voice_samples")
    os.makedirs(samples_dir, exist_ok=True)

    lines = load_lines()
    state = {
        "name": "Cyril",
        "prompt_index": 0,
        "records": {},          # prompt_index -> filepath
        "recording": False,
        "buffer": None,
        "stream": None,
        "level": 0.0,
        "take": 0,
    }
    audio_q: "queue.Queue[np.ndarray]" = queue.Queue()

    root = tk.Tk()
    root.title("Сканер голоса — Auraloom Soundboard")
    root.geometry("940x680")
    root.configure(bg="#14161a")

    fg, bg, accent, dim = "#e8e8e8", "#14161a", "#4a9eff", "#8b93a1"

    # Тёмная тема ttk, иначе progressbar выглядит как белая полоса
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Auraloom.Horizontal.TProgressbar", troughcolor="#1e2229",
                    background="#4a9eff", bordercolor="#1e2229",
                    lightcolor="#4a9eff", darkcolor="#4a9eff",
                    thickness=14, borderwidth=0)

    def lbl(text, size=11, color=None, parent=None, **kw):
        return tk.Label(parent or root, text=text, bg=bg, fg=color or fg,
                        font=("Segoe UI", size), **kw)

    lbl("Сканер голоса", 18, accent).pack(anchor="w", padx=20, pady=(18, 0))
    lbl("Нажимай «Записать» и читай подсказку. Затем — «Скопировать голос».",
        10, dim).pack(anchor="w", padx=20)

    name_row = tk.Frame(root, bg=bg)
    name_row.pack(anchor="w", padx=20, pady=(14, 6))
    lbl("Имя:", 10, dim, parent=name_row).pack(side="left")
    name_entry = tk.Entry(name_row, width=18, bg="#1e2229", fg=fg,
                          insertbackground=fg, relief="flat")
    name_entry.insert(0, state["name"])
    name_entry.pack(side="left", padx=(8, 0))

    # Переключатель языка подсказок
    lang_row = tk.Frame(root, bg=bg)
    lang_row.pack(anchor="w", padx=20, pady=(2, 6))
    lbl("Язык подсказок:", 10, dim, parent=lang_row).pack(side="left")
    lang_var = tk.StringVar(value=LANG)

    def on_lang_change(*_args) -> None:
        set_lang(lang_var.get())
        state["prompt_index"] = 0
        show_prompt()
        refresh_tree()

    for code, title in (("ru", "Русский"), ("es", "Español (акцент)")):
        tk.Radiobutton(lang_row, text=title, value=code, variable=lang_var,
                       command=on_lang_change, bg=bg, fg=fg, selectcolor="#1e2229",
                       activebackground=bg, activeforeground=fg,
                       font=("Segoe UI", 10)).pack(side="left", padx=(8, 0))

    # Блок с подсказкой
    prompt_frame = tk.LabelFrame(root, text=" Подсказка ", bg=bg, fg=dim,
                                 font=("Segoe UI", 9), padx=14, pady=12)
    prompt_frame.pack(fill="x", padx=20, pady=6)
    prompt_es = lbl("", 15, fg, parent=prompt_frame)
    prompt_es.pack(anchor="w")
    prompt_ru = lbl("", 10, dim, parent=prompt_frame)
    prompt_ru.pack(anchor="w", pady=(4, 0))

    # Индикатор уровня
    level_frame = tk.Frame(root, bg=bg)
    level_frame.pack(fill="x", padx=20, pady=(8, 4))
    lbl("Уровень:", 10, dim, parent=level_frame).pack(side="left")
    level_bar = ttk.Progressbar(level_frame, maximum=100, length=380,
                                 style="Auraloom.Horizontal.TProgressbar")
    level_bar.pack(side="left", padx=(8, 0))
    level_label = lbl("", 9, dim, parent=level_frame)
    level_label.pack(side="left", padx=8)

    # Кнопки
    btn_row = tk.Frame(root, bg=bg)
    btn_row.pack(anchor="w", padx=20, pady=10)

    status = lbl("", 10, dim)
    status.pack(anchor="w", padx=20)

    # Список прогресса
    tree_frame = tk.LabelFrame(root, text=" Записи ", bg=bg, fg=dim,
                               font=("Segoe UI", 9), padx=8, pady=6)
    tree_frame.pack(fill="both", expand=True, padx=20, pady=(10, 6))
    tree = ttk.Treeview(tree_frame, columns=("n", "text", "dur", "q"),
                         show="headings", height=12)
    style.configure("Treeview", background="#1e2229", fieldbackground="#1e2229",
                    foreground="#e8e8e8", borderwidth=0, rowheight=22)
    style.configure("Treeview.Heading", background="#2c313a", foreground="#c8cedb",
                    relief="flat")
    style.map("Treeview", background=[("selected", "#2f4a6b")])
    tree.heading("n", text="#")
    tree.heading("text", text="Подсказка")
    tree.heading("dur", text="Длина")
    tree.heading("q", text="Качество")
    tree.column("n", width=40, anchor="center")
    tree.column("text", width=430)
    tree.column("dur", width=80, anchor="center")
    tree.column("q", width=130, anchor="center")
    tree.pack(fill="both", expand=True)

    def pick_input_device() -> int | None:
        """Выбрать микрофон: пробуем каждый и берём тот, где громче и нет шума."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
        except Exception:
            return None

        candidates = [(i, d["name"]) for i, d in enumerate(devices)
                      if d["max_input_channels"] > 0]
        if not candidates:
            return None

        best, best_score = None, -1e9
        for idx, name in candidates:
            try:
                frames = int(0.9 * SR)
                rec = sd.rec(frames, samplerate=SR, channels=1, dtype="float32",
                             device=idx)
                sd.wait()
                audio = rec.squeeze()
                if len(audio) == 0:
                    continue
                peak = float(np.abs(audio).max())
                rms = float(np.sqrt((audio.astype("float64") ** 2).mean()))
                # Хороший микрофон: громко (rms) и без постоянного гула (пик >> rms)
                crest = peak / (rms + 1e-9)
                score = rms * min(crest, 6.0)
                if score > best_score:
                    best, best_score = idx, score
            except Exception:
                continue
        return best

    def show_prompt() -> None:
        idx = state["prompt_index"] % len(PROMPTS)
        es, ru = PROMPTS[idx]
        prompt_es.config(text=es.format(name=state["name"]))
        prompt_ru.config(text=ru.format(name=state["name"]))
        state["current_prompt"] = (es.format(name=state["name"]),
                                   ru.format(name=state["name"]))

    def refresh_tree() -> None:
        tree.delete(*tree.get_children())
        for i, (es, ru) in enumerate(PROMPTS):
            path = state["records"].get(i)
            if path and os.path.exists(path):
                dur = f"{sf.info(path).duration:.1f} c"
                q = "ок" if quality_report(sf.read(path, dtype="float32")[0])["ok"] else "!"
            else:
                dur, q = "-", ""
            tree.insert("", "end", values=(i + 1, es[:56], dur, q))

    def callback(indata, frames, time_info, status_flag):  # noqa: ARG001
        if status_flag:
            return
        mono = indata[:, 0] if indata.ndim > 1 else indata
        # Пишем прямо в буфер записи. Раньше данные шли в очередь, которую
        # опустошал индикатор уровня - из-за этого запись выходила пустой.
        state["buffer"].append(mono.copy())
        state["level"] = float(np.abs(mono).max())

    def start_recording() -> None:
        if state["recording"]:
            return
        state["recording"] = True
        state["take"] += 1
        state["buffer"] = []
        status.config(text="Записываю... говори!")
        rec_btn.config(state="disabled")
        stop_btn.config(state="normal")

        def _run():
            kwargs = {}
            dev = state.get("device")
            if dev is not None:
                kwargs["device"] = dev
            with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                callback=callback, blocksize=1024, **kwargs):
                while state["recording"]:
                    time.sleep(0.05)

        threading.Thread(target=_run, daemon=True).start()

    def stop_recording() -> None:
        if not state["recording"]:
            return
        state["recording"] = False
        rec_btn.config(state="normal")
        stop_btn.config(state="disabled")

        # Даём потоку записи дописать последний блок.
        time.sleep(0.15)

        chunks = state["buffer"]
        state["buffer"] = []
        if not chunks:
            status.config(text="Звук не получен — проверь микрофон (кнопка «Тест микрофона»)")
            return
        raw = np.concatenate(chunks).astype("float32")
        trimmed = trim_by_energy(raw)
        rep = quality_report(trimmed)

        idx = state["prompt_index"] % len(PROMPTS)
        path = os.path.join(samples_dir, f"take_{idx + 1:02d}.wav")
        sf.write(path, trimmed, SR, subtype="PCM_16")
        # Сырую запись тоже сохраняем - на случай, если что-то пойдет не так.
        sf.write(os.path.join(samples_dir, f"raw_{idx + 1:02d}.wav"), raw, SR, subtype="PCM_16")
        state["records"][idx] = path
        refresh_tree()

        if rep["ok"]:
            status.config(text=f"Записано: {rep['dur']:.1f} c, {rep['rms']:.3f} RMS — ок")
            state["prompt_index"] += 1
            show_prompt()
        else:
            status.config(text=f"Переделай: {rep['reason']}")

    def build_reference() -> str:
        """Собрать референс из лучших записей (по уровню и разборчивости)."""
        paths = [p for p in state["records"].values() if os.path.exists(p)]
        if not paths:
            status.config(text="Сначала запиши хотя бы одну подсказку")
            return ""
        scored = []
        for p in paths:
            audio, _ = sf.read(p, dtype="float32")
            rep = quality_report(audio)
            scored.append((rep["rms"] if rep["ok"] else 0.0, p, audio))
        scored.sort(key=lambda t: t[0], reverse=True)

        parts = []
        for _, _, audio in scored:
            parts.append(audio)
            parts.append(np.zeros(int(SR * 0.4), dtype="float32"))
        ref = np.concatenate(parts)
        ref = trim_by_energy(ref)
        peak = float(np.abs(ref).max())
        if peak > 0:
            ref = ref / peak * 0.95
        out = os.path.join(ROOT, "reference.wav")
        sf.write(out, ref, SR, subtype="PCM_16")
        return out

    def find_xtts_python() -> str:
        """Python с coqui-tts: предпочитаем venv проекта, иначе текущий."""
        local = os.path.join(ROOT, ".venv_voice", "Scripts", "python.exe")
        if os.path.exists(local):
            return local
        for cand in (r"C:\Users\cyril\AppData\Local\Temp\opencode\venv_voice\Scripts\python.exe",):
            if os.path.exists(cand):
                return cand
        return sys.executable

    def on_clone() -> None:
        ref = build_reference()
        if not ref:
            return
        dur = sf.info(ref).duration
        python_exe = find_xtts_python()
        status.config(text=f"Референс собран ({dur:.1f} c). Клонирую — это 5-15 минут...")
        root.update()

        def _work():
            cmd = [python_exe, os.path.join(ROOT, "tools", "xtts_clone.py"),
                   "--reference", ref, "--attempts", "10"]
            import subprocess
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            ok = proc.returncode == 0
            root.after(0, lambda: _finish_clone(ok, proc.stdout[-1500:], proc.stderr[-800:]))

        threading.Thread(target=_work, daemon=True).start()
        clone_btn.config(state="disabled")

    def distribute_outputs() -> None:
        """Разложить свежие файлы по папкам: ресурс + плеер."""
        import shutil
        ogg_src = os.path.join(ROOT, "out", "ogg")
        mp3_src = os.path.join(ROOT, "out", "mp3")
        for src, dst in ((ogg_src, os.path.join(ROOT, "sounds")),
                         (mp3_src, os.path.join(ROOT, "player", "mp3"))):
            os.makedirs(dst, exist_ok=True)
            for path in glob.glob(os.path.join(src, "mx_*.*")):
                shutil.copy2(path, os.path.join(dst, os.path.basename(path)))

    def _finish_clone(ok: bool, out: str, err: str) -> None:
        clone_btn.config(state="normal")
        log_path = os.path.join(ROOT, "clone_log.txt")
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(out + "\n--- STDERR ---\n" + err)
        if ok:
            distribute_outputs()
            status.config(text="Готово! Копия голоса сделана. Проверяю похожесть...")
            root.update()

            def _verify():
                import subprocess
                venv_python = find_xtts_python()
                proc = subprocess.run(
                    [venv_python, os.path.join(ROOT, "tools", "voice_similarity.py"),
                     "--reference", ref],
                    cwd=ROOT, capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
                root.after(0, lambda: _show_similarity(proc.stdout, proc.stderr))

            threading.Thread(target=_verify, daemon=True).start()
        else:
            status.config(text="Ошибка клонирования — подробности в clone_log.txt")

    def _show_similarity(out: str, err: str) -> None:
        with open(os.path.join(ROOT, "similarity_log.txt"), "w", encoding="utf-8") as fh:
            fh.write(out + "\n--- STDERR ---\n" + err)
        summary = ""
        for line in out.splitlines():
            if "Средняя схожесть" in line:
                summary = line.strip()
        status.config(text=(summary or "Проверка схожести — в similarity_log.txt") + "  (лог: similarity_log.txt)")

    rec_btn = tk.Button(btn_row, text="● Записать", command=start_recording,
                        bg="#c0392b", fg="#fff", font=("Segoe UI", 11, "bold"),
                        relief="flat", padx=16, pady=8, cursor="hand2")
    rec_btn.pack(side="left", padx=(0, 8))

    stop_btn = tk.Button(btn_row, text="■ Стоп", command=stop_recording,
                         bg="#3a3f48", fg=fg, font=("Segoe UI", 11),
                         relief="flat", padx=16, pady=8, state="disabled", cursor="hand2")
    stop_btn.pack(side="left", padx=(0, 8))

    clone_btn = tk.Button(btn_row, text="★ Скопировать голос и переозвучить всё",
                          command=on_clone, bg="#1e6f3f", fg="#fff",
                          font=("Segoe UI", 11, "bold"), relief="flat",
                          padx=16, pady=8, cursor="hand2")
    clone_btn.pack(side="left", padx=(0, 8))

    tk.Button(btn_row, text="⟳ Заново", command=lambda: (state.update(
        {"records": {}, "prompt_index": 0}), refresh_tree(), show_prompt()),
        bg="#2c313a", fg=fg, font=("Segoe UI", 10), relief="flat",
        padx=12, pady=8, cursor="hand2").pack(side="left")

    def on_similarity() -> None:
        ref = build_reference()
        if not ref:
            status.config(text="Сначала запиши подсказки")
            return
        status.config(text="Считаю схожесть голоса...")
        root.update()

        def _work():
            import subprocess
            proc = subprocess.run(
                [find_xtts_python(), os.path.join(ROOT, "tools", "voice_similarity.py"),
                 "--reference", ref],
                cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            root.after(0, lambda: _show_similarity(proc.stdout, proc.stderr))

        threading.Thread(target=_work, daemon=True).start()

    tk.Button(btn_row, text="◎ Оценить похожесть", command=on_similarity,
              bg="#2c313a", fg=fg, font=("Segoe UI", 10), relief="flat",
              padx=12, pady=8, cursor="hand2").pack(side="left", padx=(8, 0))

    def on_mic_test() -> None:
        """Проверить микрофон: записать 3 секунды и показать уровень."""
        dev = pick_input_device()
        status.config(text=f"Тест микрофона (устройство {dev})...")
        root.update()

        def _work():
            import sounddevice as sd
            frames = int(3 * SR)
            try:
                kwargs = {"device": dev} if dev is not None else {}
                rec = sd.rec(frames, samplerate=SR, channels=1, dtype="float32", **kwargs)
                sd.wait()
            except Exception as exc:  # noqa: BLE001
                root.after(0, lambda: status.config(text=f"Микрофон недоступен: {exc}"))
                return
            audio = np.asarray(rec, dtype="float32").squeeze()
            peak = float(np.abs(audio).max()) if audio.size else 0.0
            rms = float(np.sqrt((audio.astype("float64") ** 2).mean())) if audio.size else 0.0
            root.after(0, lambda: status.config(
                text=f"Микрофон: пик {peak:.3f}, RMS {rms:.4f} — "
                     + ("слышно, ок" if rms > 0.005 else "тишина, проверь устройство/уровень")))

        threading.Thread(target=_work, daemon=True).start()

    tk.Button(btn_row, text="♪ Тест микрофона", command=on_mic_test,
              bg="#2c313a", fg=fg, font=("Segoe UI", 10), relief="flat",
              padx=12, pady=8, cursor="hand2").pack(side="left", padx=(8, 0))

    def tick() -> None:
        # Уровень берём из state (его обновляет аудио-колбэк), а не из очереди:
        # очередь опустошается только при остановке записи.
        lvl = int(min(100, state["level"] * 140))
        level_bar["value"] = lvl
        if state["recording"]:
            level_label.config(text=f"{lvl}%  пишет...")
        else:
            level_label.config(text=f"{lvl}%")
        root.after(60, tick)

    show_prompt()
    refresh_tree()
    tick()

    # Автоопределение микрофона в фоне, чтобы окно сразу было готово к записи
    def _autopick():
        dev = pick_input_device()
        root.after(0, lambda: state.update({"device": dev}))

    threading.Thread(target=_autopick, daemon=True).start()

    root.mainloop()

    # После закрытия окна — спросить, собирать ли референс
    paths = [p for p in state["records"].values() if os.path.exists(p)]
    if not paths:
        return ""
    return build_reference()


def main() -> None:
    ref = run_gui()
    if ref:
        print(f"\nРеференс готов: {ref}")
        print(f"Дальше: python tools\\xtts_clone.py --reference \"{ref}\" --attempts 10")
    else:
        print("\nЗаписей нет — референс не собран.")


if __name__ == "__main__":
    main()
