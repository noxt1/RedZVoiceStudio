"""Auraloom — звуковая панель с выводом прямо в микрофон.

Вкладки:
  1. Фразы     — список реплик (пресет + свои), озвучка своим голосом
  2. Голос     — запись образца голоса и клонирование (XTTS)
  3. Микрофон  — выбор устройств, стрим реплик в микрофон, проверка маршрута,
                  глобальные горячие клавиши (работают, когда игра в фокусе)
  4. Проверка  — разборчивость, схожесть голоса, правила, синхронность
  5. В игру    — куда положить файлы для RedM/FiveM и внешнего плеера

Приложение работает и из исходников, и как собранный EXE.
"""

from __future__ import annotations

import json
import os
import re
import queue
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import tkinter as tk
from tkinter import ttk

import hotkeys as hk
import live_tab
import logpanel
import mic_bridge
import studio_core as core
import studio_paths as sp
import translate

BG, FG, DIM, ACCENT, GOOD, WARN = "#14161a", "#e8e8e8", "#8b93a1", "#4a9eff", "#7bd88f", "#e8c07a"

# Детектор зависания: сколько секунд движок может молчать.
HANG_WARN_SEC = 100       # столько секунд без ответа движка -> предупреждение
HANG_AUTO_STOP_SEC = 420  # столько секунд без ответа движка -> автостоп с отчётом

PRESET_ES = [
    "Que chido, guay!", "No manches, guay!", "Orale, carnal!", "A huevo!",
    "Neta que no manches!", "Que pedo, guay!", "Pinche cabron!",
    "Ya esta chido, aqui voy!", "Chilango de mi corazon!",
    "Ya ni me hable, por favor!", "Arriba!", "Abajo!", "No se mueva!",
    "Manos arriba!", "Alto! Alla se!", "Suelte el arma!",
    "Dispara primero!", "Me rindo!", "Auxilio!", "Que me van a matar!",
    "No me puedo mover!", "Tengo un balazo en la pierna!",
    "Socorro por favor!", "Acepto mi destino!", "No acepto, punto!",
    "Aqui esta tu dinero, no te lopinees", "Me late, no?",
    "Eso no se hace aqui", "Vete pal otro, te toca", "Ya me dio hambre",
    "Cafe con leche, por favor",
]


class _StubLabel:
    """Заглушка tk.Label для нового UI: методы вызываются, но ничего не рисуют."""

    def config(self, **kwargs):
        pass

    configure = config

    def pack(self, **kwargs):
        pass

    def pack_forget(self):
        pass

    def cget(self, key):
        return ""

    def winfo_exists(self):
        return False


class _StubPanel:
    """Заглушка LogPanel для нового UI: копит строки в памяти."""

    def __init__(self):
        self.lines = []
        self._title = ""
        self._steps = []

    def log(self, kind, text):
        self.lines.append((kind, str(text)))
        del self.lines[:-200]

    def log_text(self):
        return "\n".join(t for _k, t in self.lines)

    def begin(self, title, steps=None, total=0):
        self._title = str(title)
        self._steps = list(steps or [])
        self.lines.append(("head", self._title))

    def step(self, *a, **k):
        pass

    def set_stage(self, *a, **k):
        pass

    def progress_set(self, *a, **k):
        pass

    def finish(self, *a, **k):
        pass

    def heartbeat(self):
        pass

    def stall_warning(self, *a, **k):
        pass


class Studio:
    def __init__(self, use_new_ui: bool = False, root=None) -> None:
        try:
            sp.seed_workspace()
        except Exception as exc:  # noqa: BLE001
            # Не даём падать из-за одного файла — работаем дальше
            print(f"seed_workspace: {exc}")
        if root is not None:
            # Новый UI: корневое окно создаёт MainWindow — передаём его сюда,
            # чтобы не было двух окон (Studio не создаёт своё tk.Tk()).
            self.root = root
        elif use_new_ui:
            # Новый UI без переданного корня: окно создаст MainWindow и будет
            # назначено позже (main() делает studio.root = app.root).
            # Своё tk.Tk() не создаём — иначе появится второе пустое окно.
            self.root = None
        else:
            # Старый UI / автономный запуск: Studio владеет своим окном.
            self.root = tk.Tk()
            self.root.title("Auraloom")
            self.root.geometry("1150x950")
            self.root.configure(bg=BG)
            self.root.minsize(940, 640)
        self.use_new_ui = use_new_ui

        self.name = "Cyril"
        # tk- переменные нуждаются в существующем корневом окне.
        # В новом UI (root=None) их создаём позже, в main() после
        # studio.root = app.root.
        if self.root is not None:
            self.lang = tk.StringVar(value="ru")
        else:
            self.lang = None
        # В новом UI вкладок нет — создаём заглушки, чтобы методы
        # _voice_all / _run_job / distribute не падали на отсутствующих
        # виджетах. Реальный вывод идёт в лог движка.
        if self.use_new_ui:
            self.expr_var = None
            self.phrase_status = _StubLabel()
            self.task_panel = _StubPanel()
            self.game_status = _StubLabel()
            self.mic_status = _StubLabel()
            self.check_status = _StubLabel()
            self.voice_status = _StubLabel()
            self.bridge_info = _StubLabel()
        self.prompt_index = 0
        self.records: dict[int, str] = {}
        self.recorder = core.Recorder()
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.busy = False

        self.phrases = self._load_phrases()
        # язык банка фраз: es (по умолчанию), en, ow (олдвест), it
        self.bank_lang = "es"
        self.hotkeys = hk.GlobalHotkeys()
        self.hotkeys.set_callback(self._on_hotkey)
        # очередь действий от глобальных хоткеев: наполняет поток-читатель
        # WM_HOTKEY, разбирает главный поток (tkinter из чужого потока нельзя)
        self._hk_queue: "queue.Queue[str]" = queue.Queue()
        self.out_device: int | None = None
        self.in_device: int | None = None
        self.hotkey_enabled = False
        self._job_total = 0
        self.bridge: mic_bridge.MicBridge | None = None
        # Оверлей с субтитрами поверх игры (отдельный процесс)
        self._overlay_proc = None
        self._ov_own = ""
        self._ov_target = ""
        self._ov_peer = ""
        self._ov_peer_ru = ""
        # Ссылка на боковую панель истории (устанавливается MainWindow)
        self.sidebar = None

        # Состояние движка живого перевода
        self.engine_state = "STOPPED"  # STOPPED / LOADING / READY / STOPPING / ERROR
        self.engine_error = ""

        if not self.use_new_ui:
            self._style()
            self._header()
            self._tabs()
        else:
            # При новом UI корневое окно принадлежит MainWindow.
            # tab_live — placeholder для LiveTab; не создаём его на None.
            self.tab_live = None if self.root is None else tk.Frame(self.root, bg=BG)
        # Отложенные вызовы только если корень уже есть (в новом UI он
        # появится позже — main() перепланирует их на app.root).
        if self.root is not None:
            self.root.after(120, self._drain_log)
            self.root.after(100, self._poll_live)
            self.root.after(30, self._poll_hotkeys)
        # Всегда создаём LiveTab (нужен для нового UI — ссылка на объект,
        # даже если tab ещё не привязан к окну)
        if self.tab_live is not None:
            self._build_live()
        else:
            self.live = None

    def _poll_hotkeys(self) -> None:
        """Разобрать очередь хоткеев (главный поток)."""
        self._drain_hotkeys()
        self.root.after(30, self._poll_hotkeys)

    # ---------- оверлей ----------
    def _overlay_script(self) -> str:
        """Путь к скрипту оверлея в рабочей папке."""
        return os.path.join(sp.workspace_tools(), "overlay_win.py")

    def _overlay_file(self) -> str:
        return os.path.join(sp.workspace(), "overlay.txt")

    def toggle_overlay(self, enabled: bool) -> str:
        """Включить/выключить оверлей с текстом реплики поверх игры.

        Оверлей — ОТДЕЛЬНЫЙ ПРОЦЕСС: окно Tk в не-главном потоке не
        отображается поверх других окон (проверено замером: 0 видимых
        пикселей в потоке против 3884 в главном).
        """
        if not enabled:
            proc = getattr(self, "_overlay_proc", None)
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                self._overlay_proc = None
            try:
                if os.path.exists(self._overlay_file()):
                    os.remove(self._overlay_file())
            except Exception:
                pass
            return "оверлей выключен"
        if getattr(self, "_overlay_proc", None) is not None:
            return "оверлей уже включён"
        script = self._overlay_script()
        if not os.path.exists(script):
            return "нет скрипта оверлея"
        # отдельный интерпретатор: движок (с tkinter) или сам EXE
        engine = sp.engine_python()
        if engine and os.path.exists(engine):
            cmd = [engine, script, self._overlay_file()]
        else:
            cmd = [sys.executable, script, self._overlay_file()]
        try:
            flags = 0x08000000  # CREATE_NO_WINDOW
            self._overlay_proc = subprocess.Popen(
                cmd, cwd=os.path.dirname(script), creationflags=flags,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except Exception as exc:  # noqa: BLE001
            self._overlay_proc = None
            return f"оверлей не запустился: {exc}"
        return "оверлей включён"

    def overlay_show(self, ru: str, target: str) -> None:
        """Передать реплику в оверлей (через файл — процесс читает его сам)."""
        self._ov_own = (ru or "").strip()
        self._ov_target = (target or "").strip()
        self._write_overlay()

    def overlay_peer(self, src: str, ru: str) -> None:
        """Что сказали другие игроки — вторая строка оверлея."""
        self._ov_peer = (src or "").strip()
        self._ov_peer_ru = (ru or "").strip()
        self._write_overlay()

    def _write_overlay(self) -> None:
        """Записать обе строки оверлея в файл (его читает процесс оверлея).

        Первая строка — наша речь (русский TAB перевод), вторая — речь
        других игроков. Разделитель строк — перевод строки, чтобы текст с
        переносами не ломал разбор.
        """
        if getattr(self, "_overlay_proc", None) is None:
            return
        own = self._ov_own
        if self._ov_target:
            own = f"{own}\t{self._ov_target}"
        peer = self._ov_peer
        if self._ov_peer_ru:
            peer = f"{peer}\t{self._ov_peer_ru}"
        try:
            with open(self._overlay_file(), "w", encoding="utf-8") as fh:
                fh.write(own + "\n" + peer)
        except Exception:
            pass

    def _poll_live(self) -> None:
        """Разобрать ответы движка живого перевода."""
        live = getattr(self, "live", None)
        if live is not None:
            try:
                live.poll()
            except Exception:
                pass
        self.root.after(100, self._poll_live)

    def _build_live(self) -> None:
        """Вкладка «6. Живой перевод»."""
        self.live = live_tab.LiveTab(self)

    def _heartbeat(self) -> None:
        """Пока задача идёт — показываем, что процесс жив и сколько прошло.

        Если движок молчит дольше HANG_WARN_SEC — предупреждаем.
        Если молчит дольше HANG_AUTO_STOP_SEC — снимаем задачу сами и пишем отчёт.
        """
        if self.busy:
            panel = getattr(self, "_current_panel", None)
            if panel is not None:
                panel.heartbeat()
            silent = time.time() - getattr(self, "_last_line_at", time.time())
            if silent > HANG_AUTO_STOP_SEC:
                self._stop_job("движок не отвечает")
            elif silent > HANG_WARN_SEC:
                if panel is not None:
                    panel.stall_warning(int(silent))
        self.root.after(1000, self._heartbeat)

    def _cancel_job(self) -> None:
        if not self.busy:
            self.phrase_status.config(text="Нечего отменять")
            return
        self._stop_job("остановлено вручную")

    def _stop_job(self, reason: str) -> None:
        """Остановить задачу и написать отчёт: что сделано, что осталось."""
        import studio_core as core
        core.cancel_job()
        panel = getattr(self, "_current_panel", None)
        done = sorted(getattr(self, "_done_ids", []))
        total = [p["id"] for p in getattr(self, "_job_phrase_ids", [])]
        seconds = time.time() - getattr(self, "_job_started", time.time())
        path = ""
        try:
            path = core.write_report(
                getattr(self, "_job_title", "задача"), done, total, seconds, reason)
        except Exception as exc:  # noqa: BLE001
            path = f"(отчёт не записан: {exc})"
        msg = (f"{reason}. Готово {len(done)} из {len(total)}. Отчёт: {path}")
        self.phrase_status.config(text=msg[:120])
        if panel is not None:
            panel.log("warn", msg)
            for i, st in enumerate(panel._steps):
                if st["status"] in ("todo", "doing"):
                    panel.step(i, "fail", reason)
            panel.finish(False, msg[:80])
        self.busy = False
        self.root.after(200, self._refresh_engine)
        self.root.after(400, self._load_devices)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- данные ----------
    def _phrases_file(self) -> str:
        return os.path.join(sp.workspace(), "phrases.json")

    def _load_phrases(self) -> list[dict]:
        """Пресет (из lines.json: испанский + русский перевод) + свои фразы."""
        preset: list[dict] = []
        try:
            for line in core.load_lines():
                preset.append({"id": line["id"], "text": line["es"],
                               "ru": line.get("ru", ""),
                               "en": line.get("en", ""),
                               "ow": line.get("ow", ""),
                               "it": line.get("it", ""),
                               "hotkey": self._default_hotkey(len(preset)),
                               "cat": line.get("cat", ""), "custom": False})
        except Exception:
            for i, t in enumerate(PRESET_ES):
                preset.append({"id": f"{i + 1:02d}", "text": t, "ru": "",
                               "en": "", "ow": "", "it": "",
                               "hotkey": self._default_hotkey(i),
                               "cat": "excl", "custom": False})

        # Свои фразы из phrases.json
        custom: list[dict] = []
        path = self._phrases_file()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    saved = json.load(fh)["phrases"]
                known = {p["id"] for p in preset}
                for item in saved:
                    # id уже занят пресетом -> это дубль (пресет главнее).
                    # Иначе фраза попадёт в список дважды и движок сгенерирует
                    # один и тот же файл два раза.
                    if item["id"] in known:
                        continue
                    known.add(item["id"])
                    custom.append(item)
            except Exception:
                pass
        return preset + custom

    def _save_phrases(self) -> None:
        """Сохраняем только свои фразы — пресет каждый раз берётся из lines.json."""
        custom = [p for p in self.phrases if p.get("custom")]
        with open(self._phrases_file(), "w", encoding="utf-8") as fh:
            json.dump({"phrases": custom}, fh, ensure_ascii=False, indent=2)

    @staticmethod
    def _default_hotkey(index: int) -> str:
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
                "numpad1", "numpad2", "numpad3", "numpad4", "numpad5",
                "numpad6", "numpad7", "numpad8", "numpad9",
                "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11"]
        return keys[index] if index < len(keys) else ""

    # ---------- оформление ----------
    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TLabelframe", background=BG, foreground=DIM)
        style.configure("TLabelframe.Label", background=BG, foreground=DIM)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e2229", foreground="#c8cedb",
                        padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", "#2c313a")])
        style.configure("Treeview", background="#1e2229", fieldbackground="#1e2229",
                        foreground=FG, borderwidth=0, rowheight=24)
        style.configure("Treeview.Heading", background="#2c313a", foreground="#c8cedb",
                        relief="flat")
        style.map("Treeview", background=[("selected", "#2f4a6b")])
        style.configure("Redz.Horizontal.TProgressbar", troughcolor="#1e2229",
                        background=ACCENT, bordercolor="#1e2229",
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=14, borderwidth=0)

    def _lbl(self, parent, text="", size=10, color=None, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=color or FG,
                        font=("Segoe UI", size), **kw)

    def _btn(self, parent, text, command, bg="#2c313a", fg=FG, size=10, padx=12, pady=7):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         font=("Segoe UI", size), relief="flat", padx=padx, pady=pady,
                         cursor="hand2", activebackground="#3a414d")

    # ---------- шапка ----------
    def _header(self) -> None:
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=18, pady=(14, 4))
        self._lbl(head, "Auraloom", 18, ACCENT).pack(side="left")
        self.engine_lbl = self._lbl(head, "движок: проверяю…", 10, DIM)
        self.engine_lbl.pack(side="right")
        self._lbl(self.root, f"Рабочая папка: {sp.workspace()}", 9, DIM).pack(
            anchor="w", padx=18)

    def _tabs(self) -> None:
        nb = ttk.Notebook(self.root)
        self.nb = nb
        nb.pack(fill="both", expand=True, padx=14, pady=10)
        self.tab_phrases = tk.Frame(nb, bg=BG)
        self.tab_voice = tk.Frame(nb, bg=BG)
        self.tab_mic = tk.Frame(nb, bg=BG)
        self.tab_check = tk.Frame(nb, bg=BG)
        self.tab_game = tk.Frame(nb, bg=BG)
        self.tab_live = tk.Frame(nb, bg=BG)
        for frame, title in ((self.tab_phrases, "1. Фразы"),
                             (self.tab_voice, "2. Голос"),
                             (self.tab_mic, "3. Микрофон"),
                             (self.tab_check, "4. Проверка"),
                             (self.tab_game, "5. В игру"),
                             (self.tab_live, "6. Живой перевод")):
            nb.add(frame, text=title)
        self._build_phrases()
        self._build_voice()
        self._build_mic()
        self._build_check()
        self._build_game()
        # Устройства заполняем сразу: иначе списки микрофонов пустые,
        # пока не отменишь какую-нибудь задачу (раньше _load_devices
        # вызывался только оттуда)
        self._load_devices()

    # ---------- 1. Фразы ----------
    def _build_phrases(self) -> None:
        self._lbl(self.tab_phrases,
                  "Свои фразы можно добавлять — они озвучиваются тем же голосом.",
                  10, DIM).pack(anchor="w", padx=16, pady=(12, 4))

        add_row = tk.Frame(self.tab_phrases, bg=BG)
        add_row.pack(fill="x", padx=16, pady=4)
        self._lbl(add_row, "Новая фраза:", 10, DIM).pack(side="left")
        self.new_phrase = tk.Entry(add_row, bg="#1e2229", fg=FG, insertbackground=FG,
                                   relief="flat", font=("Segoe UI", 11))
        self.new_phrase.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.new_phrase.bind("<Return>", lambda e: self._add_phrase())
        self._btn(add_row, "+ Добавить", self._add_phrase, "#1e6f3f", "#fff", 10, 12, 6).pack(
            side="left", padx=(0, 8))
        self._btn(add_row, "▶ Озвучить моим голосом", self._voice_custom).pack(side="left")

        box = tk.LabelFrame(self.tab_phrases, text=" Фразы ", bg=BG, fg=DIM,
                            font=("Segoe UI", 9), padx=8, pady=6)
        box.pack(fill="both", expand=True, padx=16, pady=(8, 6))

        # язык банка фраз: es / en / ow (олдвест) / it
        lang_row = tk.Frame(self.tab_phrases, bg=BG)
        lang_row.pack(fill="x", padx=16, pady=(0, 4))
        self._lbl(lang_row, "Язык фраз:", 10, DIM).pack(side="left")
        self.bank_combo = ttk.Combobox(lang_row, state="readonly", width=32)
        self.bank_combo["values"] = [f"{code}: {title}"
                                     for code, title in core.lang_titles()]
        self.bank_combo.current(0)
        self.bank_combo.pack(side="left", padx=(8, 8))
        self.bank_combo.bind("<<ComboboxSelected>>", self._on_bank_lang)
        self._lbl(lang_row, "озвучка и фразы на этом языке", 9, DIM).pack(side="left")

        self.phrase_tree = ttk.Treeview(box, columns=("id", "text", "ru", "hk", "file"),
                                        show="headings", height=7)
        for col, title, width in (("id", "#", 45), ("text", "Фраза", 300),
                                  ("ru", "Перевод (рус.)", 240), ("hk", "Хоткей", 100),
                                  ("file", "Файл", 90)):
            self.phrase_tree.heading(col, text=title)
            self.phrase_tree.column(col, width=width,
                                    anchor="w" if col in ("text", "ru") else "center")
        self.phrase_tree.pack(fill="both", expand=True)

        btns = tk.Frame(self.tab_phrases, bg=BG)
        btns.pack(anchor="w", padx=16, pady=(0, 12))
        self._btn(btns, "▶ Проиграть выбранное", self._play_selected).pack(side="left", padx=(0, 8))
        self._btn(btns, "🗑 Удалить фразу", self._del_phrase).pack(side="left", padx=(0, 8))
        self._btn(btns, "★ Озвучить всё моим голосом", self._voice_all, "#1e6f3f", "#fff", 10, 14, 8).pack(side="left", padx=(0, 8))
        self._btn(btns, "■ Отменить", self._cancel_job, "#7a2f2f", "#fff", 10, 12, 8).pack(side="left")

        # Живость интонации: 0 — ровно, 3 — максимум выразительности
        self._lbl(btns, "Живость:", 10, DIM).pack(side="left", padx=(16, 4))
        self.expr_var = tk.IntVar(value=2)
        expr_scale = ttk.Scale(btns, from_=0, to=3, variable=self.expr_var,
                                orient="horizontal", length=110)
        expr_scale.pack(side="left")
        self.expr_lbl = self._lbl(btns, "2", 10, ACCENT)
        self.expr_lbl.pack(side="left", padx=(4, 0))
        self.expr_var.trace_add("write", lambda *_: self.expr_lbl.config(
            text=str(self.expr_var.get())))
        self.phrase_status = self._lbl(self.tab_phrases, "", 10, DIM)
        self.phrase_status.pack(anchor="w", padx=16, pady=(0, 4))
        # прогресс показывает панель шагов (app/logpanel.py)
        self.progress_lbl = None

        self.task_panel = logpanel.LogPanel(self.tab_phrases, height_steps=4, height_log=7)
        self.task_panel.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self._refresh_phrases()

    def _refresh_phrases(self) -> None:
        self.phrase_tree.delete(*self.phrase_tree.get_children())
        for row in self.phrases:
            path = self._phrase_path(row["id"])
            self.phrase_tree.insert("", "end", values=(
                row["id"], self._phrase_text(row)[:44],
                (row.get("ru") or "")[:40],
                row.get("hotkey", ""),
                "есть" if os.path.exists(path) else "—"))

    # ---------- язык банка фраз ----------
    def _bank_code(self) -> str:
        """Код выбранного языка фраз (es по умолчанию).

        В новом UI self.bank_lang — обычная строка (не tk-переменная).
        В legacy читается из combobox.
        """
        try:
            lang = getattr(self, "bank_lang", None)
            if isinstance(lang, str) and lang:
                return lang
            if lang is not None and hasattr(lang, "get"):
                value = lang.get()
                return value.split(":")[0].strip() if value else "es"
            value = self.bank_combo.get()
            return value.split(":")[0].strip() if value else "es"
        except Exception:
            return "es"

    def _phrase_text(self, phrase: dict) -> str:
        """Текст фразы на выбранном языке."""
        code = self._bank_code()
        if code == "es":
            return phrase.get("text", "")
        return phrase.get(code) or phrase.get("text", "")

    def _phrase_path(self, phrase_id: str) -> str:
        """Файл озвучки фразы для выбранного языка.

        Для не-испанского — с суффиксом (mx_01_en.mp3). Если такого файла
        нет, берём испанский — лучше услышать фразу на другом языке,
        чем ничего.
        """
        out = sp.output_paths()["out_mp3"]
        suffix = core.lang_suffix(self._bank_code())
        if suffix:
            path = os.path.join(out, f"mx_{phrase_id}{suffix}.mp3")
            if os.path.exists(path):
                return path
        return os.path.join(out, f"mx_{phrase_id}.mp3")

    def _on_bank_lang(self, _event=None) -> None:
        """Сменили язык фраз — обновляем список и показываем язык."""
        code = self._bank_code()
        self.bank_lang = code
        self._refresh_phrases()
        self.phrase_status.config(
            text=f"Язык фраз: {core.lang_title(code)} — озвучь фразы на нём")

    def _add_phrase(self) -> None:
        text = self.new_phrase.get().strip()
        if not text:
            return
        # Русскую фразу переводим сразу на все языки — чтобы её можно было
        # озвучить и обыграть на любом из них без повторного перевода.
        langs = translate.translate_all_languages(text)
        es_text = langs["es"]
        used = {p.get("hotkey") for p in self.phrases}
        free = [k for k in [str(i) for i in range(1, 10)] + ["0"] +
                [f"numpad{i}" for i in range(1, 10)] +
                [f"f{i}" for i in range(1, 13)] if k not in used]
        idx = len(self.phrases) + 1
        self.phrases.append({"id": f"{idx:02d}", "text": es_text,
                             "ru": text,
                             "en": langs["en"], "ow": langs["ow"],
                             "it": langs["it"],
                             "hotkey": free[0] if free else "",
                             "cat": "custom", "custom": True})
        self.new_phrase.delete(0, "end")
        self._save_phrases()
        self._refresh_phrases()
        if es_text != text:
            self.phrase_status.config(text=f"Перевёл: «{text}» → «{es_text}»")
        else:
            self.phrase_status.config(text="Фраза добавлена. Озвучь её кнопкой слева.")

    def _del_phrase(self) -> None:
        sel = self.phrase_tree.selection()
        if not sel:
            return
        idx = self.phrase_tree.index(sel[0])
        removed = self.phrases.pop(idx)
        self._save_phrases()
        self._refresh_phrases()
        self.phrase_status.config(text=f"Удалено: {removed['text'][:40]}")

    def _voice_custom(self) -> None:
        try:
            sel = self.phrase_tree.selection()
        except Exception:
            sel = ()
        if not sel:
            self.phrase_status.config(text="Выбери фразу в списке")
            return
        idx = self.phrase_tree.index(sel[0])
        phrase = self.phrases[idx]
        try:
            ref = sp.active_reference()
        except Exception:
            ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.phrase_status.config(text="Нет образца голоса — запиши его на вкладке «Голос»")
            return
        self._job_total = 1
        self.phrase_status.config(text=f"Озвучиваю: {phrase['text'][:40]}…")
        # tkinter-переменные читаем ТОЛЬКО в главном потоке: из рабочего
        # потока .get() падает (RuntimeError: main thread is not in main loop)
        try:
            expr = self.expr_var.get()
        except Exception:
            expr = 2
        lang = self._bank_code()
        text = self._phrase_text(phrase)

        def _job(cb):
            code = core.clone_one(text, ref, phrase["id"], cb,
                                  expressiveness=expr, lang=lang)
            if code == 0:
                moved = core.distribute()
                cb(f"Разложено: {moved['ogg']} ogg -> sounds/, {moved['mp3']} mp3 -> player/mp3/")
            return code

        self._run_job(
            f"Озвучка фразы: {phrase['text'][:36]}",
            _job,
            status=self.phrase_status, total=1,
            steps=["Проверка образца голоса", "Загрузка модели XTTS",
                   "Генерация фразы (XTTS)", "Проверка разборчивости",
                   "Сохранение и раскладка"])

    def _voice_all(self) -> None:
        # reference активного профиля (или общий, если профиль не выбран)
        try:
            ref = sp.active_reference()
        except Exception:
            ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.phrase_status.config(text="Нет образца голоса — запиши его на вкладке «Голос»")
            return
        payload = [{"id": p["id"], "text": self._phrase_text(p), "ru": p.get("ru", "")}
                   for p in self.phrases]
        self._job_total = len(payload)
        self._job_phrase_ids = [{"id": p["id"]} for p in payload]
        # tkinter-переменные читаем ТОЛЬКО в главном потоке.
        # В новом UI expr_var не создаётся — берём безопасное значение.
        try:
            expr = self.expr_var.get()
        except Exception:
            expr = 2
        lang = self._bank_code()

        def _job(cb):
            code = core.clone_all(ref, 8, cb, texts=payload,
                                  expressiveness=expr, lang=lang)
            if code == 0:
                moved = core.distribute()
                cb(f"Разложено: {moved['ogg']} ogg -> sounds/, {moved['mp3']} mp3 -> player/mp3/")
            return code

        self._run_job(
            f"Озвучка {len(payload)} фраз твоим голосом",
            _job,
            status=self.phrase_status, total=len(payload),
            steps=["Проверка образца голоса", "Загрузка модели XTTS",
                   "Генерация фраз (XTTS)", "Проверка разборчивости",
                   "Раскладка в sounds/ и player/mp3/"])

    def _sync_out_combo(self, device: int | None) -> None:
        """Показать выбранное устройство вывода в обоих списках.

        Списки «Играть в устройство» (вкладка 3) и «Играть перевод в»
        (вкладка 6) — об одном и том же устройстве; иначе перевод уходит
        в наушники, а в кабель (и в Discord) идёт тишина.
        """
        if device is None:
            return
        try:
            for combo, values in ((self.out_combo, self._out_list),
                                  (getattr(self.live, "out_combo", None),
                                   getattr(self.live, "_outputs", []))):
                if combo is None:
                    continue
                for idx, (i, _n) in enumerate(values):
                    if i == device:
                        combo.current(idx)
                        break
        except Exception:
            pass

    def _setup_cable(self) -> None:
        """Настроить маршрут под виртуальный кабель (одна кнопка).

        Делает всё, что нужно, чтобы тебя слышали в Discord/игре:
          1. выход = «CABLE Input» (туда играем);
          2. микрофон = твой реальный (Fifine);
          3. мост включён (твоя речь + перевод в одном потоке);
          4. подсказка, какой микрофон выбрать в игре.
        """
        try:
            import cable as cable_mod
            devs = cable_mod.cable_devices()
        except Exception:
            devs = {}
        if not devs.get("output"):
            self.mic_status.config(
                text="Кабель не найден. Нажми «Установить мост (VB-CABLE)».")
            return

        # 1. выход = CABLE Input
        render_idx, render_name = devs["output"]
        capture_name = devs.get("input", (0, "CABLE Output"))[1]
        self.out_device = render_idx
        self._sync_out_combo(render_idx)

        # 2. микрофон — реальный (Fifine), не служебный
        try:
            inputs, _outputs = hk.list_devices()
            for i, n in inputs:
                if any(g in n.lower() for g in ("стерео микшер", "stereo mix",
                                               "первичный драйвер", "cable",
                                               "vb-audio")):
                    continue
                self.in_device = i
                for idx, (ii, _nn) in enumerate(getattr(self.live, "_inputs", [])):
                    if ii == i:
                        self.live.mic_combo.current(idx)
                        break
                for idx, (ii, _nn) in enumerate(self._in_list):
                    if ii == i:
                        self.in_combo.current(idx)
                        break
                break
        except Exception:
            pass

        # 3. мост
        if self.bridge is not None and self.bridge.running:
            self._toggle_bridge()      # выключить, чтобы пересоздать с новым выходом
        self._toggle_bridge()          # включить с CABLE Input

        self.mic_status.config(
            text=f"Готово: играем в «{render_name}». В Discord/игре выбери "
                 f"микрофоном «{capture_name}» — услышат и тебя, и перевод.")

    def _toggle_bridge(self) -> None:
        """Включить/выключить мост микрофон -> выход.

        Маршрут выбирается автоматически:
          * если установлен виртуальный кабель (VB-CABLE) — играем в
            «CABLE Input», а микрофоном в игре выбирается «CABLE Output»;
          * иначе — встроенный «Стерео микшер» (его RedM не показывает).
        """
        if self.bridge is not None and self.bridge.running:
            self.bridge.stop()
            self.bridge = None
            self.bridge_btn.config(text="▶ Включить мост", bg="#c0392b", fg="#fff")
            self.bridge_info.config(text="мост выключен")
            return

        ok, msg = self._start_bridge()
        if not ok:
            self.bridge_info.config(text=msg)
            return
        self.bridge_btn.config(text="■ Выключить мост", bg="#1e6f3f", fg="#fff")
        self.bridge_info.config(text=msg)
        self._sync_out_combo(self.out_device)
        self.mic_status.config(text=msg)
        return

    def _toggle_bridge_legacy_unused(self) -> None:
        """Старая реализация (не используется) — оставлена как справка."""
        try:
            inputs, outputs = hk.list_devices()
        except Exception as exc:  # noqa: BLE001
            self.bridge_info.config(text=f"аудиоустройства: {exc}")
            return

        # --- 1. виртуальный кабель (лучший вариант) ---
        render_idx = render_name = ""
        capture_name = ""
        try:
            import cable as cable_mod
            devs = cable_mod.cable_devices()
        except Exception:
            devs = {}
        if devs.get("output"):
            render_idx, render_name = devs["output"]     # CABLE Input (воспроизведение)
            capture_name = devs.get("input", (0, "CABLE Output"))[1]

        # --- 2. запасной путь: Stereo Mix ---
        if render_idx is None:
            mix_idx, mix_name = hk.find_stereo_mix(inputs)
            if mix_idx is None:
                self.bridge_info.config(
                    text="Нет ни виртуального кабеля, ни Stereo Mix. "
                         "Нажми «Установить мост».")
                return
            render_idx, render_name = hk.find_render_for_capture(inputs, outputs)
            capture_name = mix_name
            if render_idx is None:
                self.bridge_info.config(text="не нашёл устройство вывода под Stereo Mix")
                return

        # микрофон для речи: выбранный пользователем, иначе запомненный,
        # иначе автоподбор
        mic_idx = self.in_device
        if mic_idx is None:
            mic_idx, _ = core.recalled_mic()
        mic_name = ""
        if mic_idx is not None:
            for i, n in inputs:
                if i == mic_idx:
                    mic_name = n
                    break
        if mic_idx is None:
            mic_idx, mic_name = core.pick_input_device()
        if mic_idx is None:
            self.bridge_info.config(text="микрофон не найден")
            return

        # устройство, на котором игрок слушает себя (по умолчанию системы)
        monitor_idx = None
        try:
            import sounddevice as sd
            monitor_idx = sd.default.device[1]
        except Exception:
            monitor_idx = None

        # громкость перевода в наушниках (из ползунка вкладки 6)
        monitor_vol = 0.8
        live = getattr(self, "live", None)
        if live is not None:
            try:
                monitor_vol = float(live.monitor_vol.get()) / 100.0
            except Exception:
                monitor_vol = 0.8

        bridge = mic_bridge.MicBridge(mic_device=mic_idx, render_device=render_idx,
                                      monitor_device=monitor_idx,
                                      monitor_gain=monitor_vol)
        try:
            bridge.start()
        except Exception as exc:  # noqa: BLE001
            self.bridge_info.config(text=f"не запустился: {exc}")
            return

        self.bridge = bridge
        self.bridge_btn.config(text="■ Выключить мост", bg="#1e6f3f", fg="#fff")
        self.bridge_info.config(
            text=f"мост включён: речь ← «{mic_name}», выход ← «{render_name}»")
        # вкладка «6. Живой перевод» знает про режим «только испанский» —
        # применяем его к свежесозданному мосту
        live = getattr(self, "live", None)
        if live is not None:
            live._apply_mute()
        # запоминаем выбранный выход — живой перевод пойдёт туда же
        self.out_device = render_idx
        self._sync_out_combo(render_idx)
        self.mic_status.config(
            text=f"В игре/Discord выбери микрофоном «{capture_name}» — "
                 f"услышат и твою речь, и перевод.")
        if monitor_idx is not None and monitor_idx == render_idx:
            self.bridge_info.config(
                text=f"мост включён: речь ← «{mic_name}», выход ← «{render_name}». "
                     f"Лучше надень наушники, иначе услышишь себя.")

    def _start_bridge(self) -> tuple[bool, str]:
        """Запустить мост микрофон -> выход (без обращения к UI).

        Возвращает (ok, сообщение). Используется и старым UI, и новым.
        """
        try:
            inputs, outputs = hk.list_devices()
        except Exception as exc:  # noqa: BLE001
            return False, f"аудиоустройства: {exc}"

        # --- 1. виртуальный кабель (лучший вариант) ---
        render_idx = render_name = ""
        capture_name = ""
        try:
            import cable as cable_mod
            devs = cable_mod.cable_devices()
        except Exception:
            devs = {}
        if devs.get("output"):
            render_idx, render_name = devs["output"]
            capture_name = devs.get("input", (0, "CABLE Output"))[1]

        # --- 2. запасной путь: Stereo Mix ---
        if render_idx is None:
            mix_idx, mix_name = hk.find_stereo_mix(inputs)
            if mix_idx is None:
                return False, ("нет ни виртуального кабеля, ни Stereo Mix — "
                               "установи VB-CABLE отдельно (vb-audio.com)")
            render_idx, render_name = hk.find_render_for_capture(inputs, outputs)
            capture_name = mix_name
            if render_idx is None:
                return False, "не нашёл устройство вывода под Stereo Mix"

        # микрофон для речи: выбранный пользователем, иначе запомненный,
        # иначе автоподбор
        mic_idx = self.in_device
        mic_name = ""
        if mic_idx is not None:
            for i, n in inputs:
                if i == mic_idx:
                    mic_name = n
                    break
            # если выбран служебный/кабельный — берём реальный
            if mic_name and any(g in mic_name.lower() for g in
                                ("стерео микшер", "stereo mix", "первичный драйвер",
                                 "primary sound capture", "переназначение звуковых",
                                 "cable output", "vb-audio")):
                mic_idx = None
        if mic_idx is None:
            mic_idx, _ = core.recalled_mic()
            if mic_idx is not None:
                for i, n in inputs:
                    if i == mic_idx:
                        mic_name = n
                        break
        if mic_idx is None:
            mic_idx, mic_name = core.pick_input_device()
        if mic_idx is None:
            return False, "микрофон не найден"

        # устройство, на котором игрок слушает себя (по умолчанию системы)
        monitor_idx = None
        try:
            import sounddevice as sd
            monitor_idx = sd.default.device[1]
        except Exception:
            monitor_idx = None

        # громкость перевода в наушниках (из ползунка живой вкладки)
        monitor_vol = 0.8
        # громкость перевода в кабеле (как слышат абоненты в игре)
        phrase_vol = 1.0
        # общая громкость всего, что уходит в кабель (и речь, и перевод)
        out_vol = 1.0
        live = getattr(self, "live", None)
        if live is not None:
            try:
                monitor_vol = float(live.monitor_vol.get()) / 100.0
            except Exception:
                monitor_vol = 0.8
            try:
                out_vol = float(live.bridge_out_vol.get()) / 100.0
            except Exception:
                out_vol = 1.0

        # Сквозной русский ТОЛЬКО если вывод — подтверждённый виртуальный
        # кабель. В запасном пути через Stereo Mix output физический —
        # туда микрофон идти не должен (иначе слышно себя в наушниках).
        cable_ok = bool(devs.get("output")) and hk.is_virtual_cable(render_name)
        bridge = mic_bridge.MicBridge(mic_device=mic_idx, render_device=render_idx,
                                      mic_gain=1.0 if cable_ok else 0.0,
                                      monitor_device=monitor_idx,
                                      monitor_gain=monitor_vol,
                                      phrase_gain=phrase_vol)
        bridge.out_gain = out_vol
        if cable_ok:
            bridge.set_duck(False)
        try:
            bridge.start()
        except Exception as exc:  # noqa: BLE001
            return False, f"не запустился: {exc}"

        self.bridge = bridge
        # вкладка «Живой перевод» знает про режим «только испанский» —
        # применяем его к свежесозданному мосту
        if live is not None:
            try:
                live._apply_mute()
            except Exception:
                pass
        # запоминаем выбранный выход — живой перевод пойдёт туда же
        self.out_device = render_idx
        return True, (f"мост включён: речь ← «{mic_name}», выход ← «{render_name}». "
                      f"В игре/Discord выбери микрофоном «{capture_name}».")

    def _check_bridge(self) -> None:
        """Проверить, что мост реально передаёт сигнал."""
        if self.bridge is None or not self.bridge.running:
            self.bridge_info.config(text="мост не запущен")
            return
        self.bridge_info.config(text="проверяю… говори что-нибудь…")
        self.root.update()
        time.sleep(2.0)
        st = self.bridge.status()
        self.bridge_info.config(
            text=f"микрофон: {st['mic_peak']:.3f} | на выходе: {st['out_peak']:.3f} "
                 + ("— сигнал идёт" if st["out_peak"] > 0.005 else "— тишина, проверь микрофон"))

    def _play_selected(self) -> None:
        sel = self.phrase_tree.selection()
        if not sel:
            return
        idx = self.phrase_tree.index(sel[0])
        phrase = self.phrases[idx]
        path = self._phrase_path(phrase["id"])
        self._play_path(path, self._phrase_text(phrase))

    def _play_path(self, path: str, label: str = "") -> None:
        if not os.path.exists(path):
            self.phrase_status.config(text="Файла нет — сначала озвучь фразу")
            return
        # Если включён мост — фраза идёт в него, тогда её слышат все
        if self.bridge is not None and self.bridge.running:
            if self.bridge.play_phrase(path):
                self.phrase_status.config(text=f"▶ {label or os.path.basename(path)} (через мост)")
            else:
                self.phrase_status.config(text="не удалось подмешать фразу")
            return
        try:
            hk.play_file(path, self.out_device)
            self.phrase_status.config(text=f"▶ {label or os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            self.phrase_status.config(text=f"Ошибка воспроизведения: {exc}")

    # ---------- 2. Голос ----------
    def _build_voice(self) -> None:
        self._lbl(self.tab_voice,
                  "Запиши 5-8 подсказок — по ним XTTS поймёт твой голос. "
                  "Русский и испанский варианты на выбор.",
                  10, DIM).pack(anchor="w", padx=16, pady=(12, 4))

        top = tk.Frame(self.tab_voice, bg=BG)
        top.pack(fill="x", padx=16, pady=4)
        self._lbl(top, "Имя:", 10, DIM).pack(side="left")
        self.name_entry = tk.Entry(top, width=16, bg="#1e2229", fg=FG,
                                   insertbackground=FG, relief="flat")
        self.name_entry.insert(0, self.name)
        self.name_entry.pack(side="left", padx=(6, 14))
        self._lbl(top, "Подсказки:", 10, DIM).pack(side="left")
        for code, title in (("ru", "Русский"), ("es", "Español")):
            tk.Radiobutton(top, text=title, value=code, variable=self.lang,
                           command=self._reload_prompts, bg=BG, fg=FG,
                           selectcolor="#1e2229", activebackground=BG,
                           activeforeground=FG, font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

        box = tk.LabelFrame(self.tab_voice, text=" Читай это ", bg=BG, fg=DIM,
                            font=("Segoe UI", 9), padx=14, pady=12)
        box.pack(fill="x", padx=16, pady=6)
        self.prompt_lbl = self._lbl(box, "", 15)
        self.prompt_lbl.pack(anchor="w")

        lvl = tk.Frame(self.tab_voice, bg=BG)
        lvl.pack(fill="x", padx=16, pady=(4, 8))
        self._lbl(lvl, "Уровень:", 10, DIM).pack(side="left")
        self.level_bar = ttk.Progressbar(lvl, maximum=100, length=360,
                                         style="Redz.Horizontal.TProgressbar")
        self.level_bar.pack(side="left", padx=(8, 0))
        self.level_lbl = self._lbl(lvl, "0%", 9, DIM)
        self.level_lbl.pack(side="left", padx=8)

        btns = tk.Frame(self.tab_voice, bg=BG)
        btns.pack(anchor="w", padx=16, pady=4)
        self.rec_btn = self._btn(btns, "● Записать", self._start_rec, "#c0392b", "#fff", 11, 16, 8)
        self.rec_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = self._btn(btns, "■ Стоп", self._stop_rec, "#3a3f48", FG, 11, 16, 8)
        self.stop_btn.pack(side="left", padx=(0, 8))
        self.stop_btn.config(state="disabled")
        self._btn(btns, "♪ Тест микрофона", self._mic_test).pack(side="left", padx=(0, 8))
        self._btn(btns, "⟳ Заново", self._reset_record).pack(side="left", padx=(0, 8))
        self._btn(btns, "★ Собрать образец голоса", self._build_ref, "#1e6f3f", "#fff", 10, 14, 8).pack(side="left")

        self.voice_status = self._lbl(self.tab_voice, "", 10, DIM)
        self.voice_status.pack(anchor="w", padx=16, pady=(6, 2))

        rec_box = tk.LabelFrame(self.tab_voice, text=" Записи ", bg=BG, fg=DIM,
                                font=("Segoe UI", 9), padx=8, pady=6)
        rec_box.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.tree = ttk.Treeview(rec_box, columns=("n", "text", "dur", "q"), show="headings")
        for col, title, width in (("n", "#", 40), ("text", "Подсказка", 430),
                                  ("dur", "Длина", 80), ("q", "Качество", 120)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="center" if col != "text" else "w")
        self.tree.pack(fill="both", expand=True)
        self._reload_prompts()

    def _reload_prompts(self) -> None:
        self.prompt_index = 0
        self._show_prompt()
        self._refresh_tree()

    def _prompts(self) -> list[str]:
        base = core.PROMPTS_ES if self.lang.get() == "es" else core.PROMPTS_RU
        return [p.format(name=self.name) for p in base]

    def _show_prompt(self) -> None:
        prompts = self._prompts()
        self.prompt_lbl.config(text=prompts[self.prompt_index % len(prompts)])

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        import soundfile as sf
        for i, text in enumerate(self._prompts()):
            path = self.records.get(i)
            dur = q = "-"
            if path and os.path.exists(path):
                try:
                    info = sf.info(path)
                    dur = f"{info.duration:.1f} c"
                    a, file_sr = sf.read(path, dtype="float32")
                    q = "ок" if core.quality_report(a, int(file_sr))["ok"] else "!"
                except Exception:
                    pass
            self.tree.insert("", "end", values=(i + 1, text[:52], dur, q))

    def _start_rec(self) -> None:
        if self.recorder.recording:
            return
        self.name = self.name_entry.get().strip() or "Cyril"
        try:
            self.recorder.start(self.recorder.device)
            if self.recorder.device is not None:
                import sounddevice as sd
                name = sd.query_devices(self.recorder.device)["name"]
                core.remember_mic(self.recorder.device, name)
        except Exception as exc:  # noqa: BLE001
            self.voice_status.config(text=f"Микрофон недоступен: {exc}")
            return
        self.rec_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.voice_status.config(text="Пишу… говори!")

    def _stop_rec(self) -> None:
        if not self.recorder.recording:
            return
        raw = self.recorder.stop()
        self.rec_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        if len(raw) == 0:
            self.voice_status.config(text="Звук не получен — нажми «Тест микрофона»")
            return
        trimmed = core.trim_by_energy(raw, self.recorder.sr)
        # репорты качества считаются по РЕАЛЬНОЙ частоте потока,
        # иначе длительность и пороги неверные
        rep = core.quality_report(trimmed, self.recorder.sr)
        idx = self.prompt_index % len(self._prompts())
        samples = sp.output_paths()["samples"]
        path = os.path.join(samples, f"take_{idx + 1:02d}.wav")
        import soundfile as sf
        # ВАЖНО: пишем с фактической частотой потока, иначе файл с меткой
        # 44100 при данных 16000 проигрывается в 2.75 раза быстрее («писк»).
        sf.write(path, trimmed, self.recorder.sr, subtype="PCM_16")
        self.records[idx] = path
        self._refresh_tree()
        if rep["ok"]:
            self.voice_status.config(text=f"Записано: {rep['dur']:.1f} c — ок")
            self.prompt_index += 1
            self._show_prompt()
        else:
            self.voice_status.config(text=f"Переделай: {rep['reason']}")

    def _mic_test(self) -> None:
        self.voice_status.config(text="Проверяю микрофон…")

        def _work():
            dev, name = core.pick_input_device()
            if dev is None:
                self.root.after(0, lambda: self.voice_status.config(text=f"Микрофон: {name}"))
                return
            self.recorder.device = dev
            res = core.test_microphone(dev)
            self.root.after(0, lambda: self.voice_status.config(
                text=f"Микрофон «{name}»: пик {res['peak']:.3f}, RMS {res['rms']:.4f} — {res['verdict']}"))

        threading.Thread(target=_work, daemon=True).start()

    def _reset_record(self) -> None:
        self.records.clear()
        self.prompt_index = 0
        self._reload_prompts()
        self.voice_status.config(text="Записи сброшены")

    def _build_ref(self) -> None:
        try:
            ref = sp.active_reference()
        except Exception:
            ref = sp.output_paths()["reference"]
        res = core.build_reference(list(self.records.values()), ref)
        if not res["ok"]:
            self.voice_status.config(text="Сначала запиши хотя бы одну подсказку")
            return
        self.voice_status.config(
            text=f"Образец готов: {res['duration']:.1f} c из {res['count']} записей")

    # ---------- 3. Микрофон ----------
    def _build_mic(self) -> None:
        self._lbl(self.tab_mic,
                  "Настройка маршрута: куда играть реплики, чтобы их слышали в RP.",
                  10, DIM).pack(anchor="w", padx=16, pady=(12, 4))

        dev_box = tk.LabelFrame(self.tab_mic, text=" Устройства ", bg=BG, fg=DIM,
                                font=("Segoe UI", 9), padx=14, pady=10)
        dev_box.pack(fill="x", padx=16, pady=6)

        row1 = tk.Frame(dev_box, bg=BG)
        row1.pack(fill="x", pady=3)
        self._lbl(row1, "Играть в устройство:", 10, DIM).pack(side="left")
        self.out_combo = ttk.Combobox(row1, state="readonly", width=62)
        self.out_combo.pack(side="left", padx=(8, 0))

        row2 = tk.Frame(dev_box, bg=BG)
        row2.pack(fill="x", pady=3)
        self._lbl(row2, "Микрофон (для проверки):", 10, DIM).pack(side="left")
        self.in_combo = ttk.Combobox(row2, state="readonly", width=62)
        self.in_combo.pack(side="left", padx=(8, 0))

        row3 = tk.Frame(dev_box, bg=BG)
        row3.pack(fill="x", pady=3)
        self._lbl(row3, "Громкость:", 10, DIM).pack(side="left")
        self.vol_var = tk.DoubleVar(value=1.0)
        vol = ttk.Scale(row3, from_=0.0, to=1.5, variable=self.vol_var, orient="horizontal",
                        length=300)
        vol.pack(side="left", padx=(8, 0))
        self.vol_lbl = self._lbl(row3, "100%", 9, DIM)
        self.vol_lbl.pack(side="left", padx=8)
        self.vol_var.trace_add("write", lambda *_: self.vol_lbl.config(
            text=f"{int(self.vol_var.get() * 100)}%"))

        btns = tk.Frame(self.tab_mic, bg=BG)
        btns.pack(anchor="w", padx=16, pady=4)
        # главное действие — настроить маршрут под кабель
        self._btn(btns, "⚡ Настроить под кабель", self._setup_cable,
                  "#1e6f3f", "#fff", 10, 14, 8).pack(side="left", padx=(0, 8))
        self.bridge_btn = self._btn(btns, "◉ Включить мост", self._toggle_bridge,
                                    "#c0392b", "#fff", 10, 14, 8).pack(side="left", padx=(0, 8))
        self._btn(btns, "◎ Проверить мост", self._check_bridge).pack(
            side="left", padx=(0, 8))

        btns2 = tk.Frame(self.tab_mic, bg=BG)
        btns2.pack(anchor="w", padx=16, pady=(2, 4))
        self._btn(btns2, "♪ Тест: реплика в микрофон", self._route_test).pack(
            side="left", padx=(0, 8))
        self._btn(btns2, "◎ Проверить маршрут (уровень микрофона)",
                  self._measure_route).pack(side="left", padx=(0, 8))
        self.hk_btn = self._btn(btns2, "⌨ Включить глобальные хоткеи", self._toggle_hotkeys,
                                "#1e6f3f", "#fff", 10, 14, 8).pack(side="left", padx=(0, 8))
        self._btn(btns2, "⬇ Установить мост (VB-CABLE)", self._install_cable).pack(
            side="left", padx=(0, 8))
        self._btn(btns2, "🔍 Диагностика устройств", self._diag_devices).pack(
            side="left", padx=(0, 8))
        self._btn(btns2, "🔄 Обновить список", self._load_devices).pack(
            side="left", padx=(0, 8))

        # --- Мост в микрофон: без установки, без сервера, без правки файлов ---
        bridge_box = tk.LabelFrame(self.tab_mic, text=" Мост в микрофон (ничего ставить не надо) ",
                                   bg=BG, fg=DIM, font=("Segoe UI", 9), padx=14, pady=10)
        bridge_box.pack(fill="x", padx=16, pady=(8, 4))
        try:
            import cable as _cable
            _cable_installed = bool(_cable.cable_devices())
        except Exception:
            _cable_installed = False

        if _cable_installed:
            route_text = (
                "Виртуальный кабель УСТАНОВЛЕН. Всё, что нужно:\n"
                "  1. Нажми «⚡ Настроить под кабель» — приложение выберет\n"
                "     «CABLE Input» как выход и включит мост (твоя речь + фразы).\n"
                "  2. В Discord/игре выбери микрофоном «CABLE Output».\n"
                "  3. Всё: тебя слышат по-русски, а перевод идёт по-испански.\n\n"
                "Без моста в кабель попадает ТОЛЬКО перевод — твою речь\n"
                "микрофон не передаёт, и в Discord тебя не будет слышно.\n"
            )
        else:
            route_text = (
                "Виртуального кабеля в системе нет. Как поставить:\n"
                "  1. Нажми «⬇ Установить мост (VB-CABLE)» — установщик УЖЕ\n"
                "     скачан (папка installers рядом с программой): сайт\n"
                "     vb-audio с этой машины недоступен, качали с зеркала.\n"
                "  2. В окне установщика нажми «Install Driver», потом «OK».\n"
                "  3. Нажми «◎ Проверить мост» — приложение найдёт устройства.\n"
                "  4. Нажми «⚡ Настроить под кабель».\n"
                "  5. В игре микрофоном выбери «CABLE Output», играть — в «CABLE Input».\n\n"
            )

        bridge_text = (
            "Мост смешивает твою речь и фразы в один поток и отдаёт его в устройство,\n"
            "которое ты укажешь. Дальше это устройство выбирается микрофоном в игре.\n\n"
            "Что реально доступно на этой машине (проверено):\n"
            "  • «Стерео микшер (Realtek USB Audio)» ЖИВОЙ (работает на 44100 Гц),\n"
            "    но игра (RedM/Mumble) его в списке микрофонов НЕ показывает.\n"
            "  • Игра показывает только реальные микрофоны: Fifine и Razer.\n\n"
            + route_text +
            "Альтернативы:\n"
            "  A. Серверный ресурс (вкладка «В игру») — 0 установок, но нужен сервер.\n"
            "  C. Stereo Mix как микрофон по умолчанию (mmsys.cpl -> Запись -> Стерео\n"
            "     микшер -> Свойства -> По умолчанию). Сработает, только если в игре\n"
            "     есть пункт «Системное устройство»."
        )
        self._lbl(bridge_box, bridge_text, 10, FG).pack(anchor="w")

        bridge_btns = tk.Frame(bridge_box, bg=BG)
        bridge_btns.pack(anchor="w", pady=(8, 0))
        # кнопки моста вынесены наверх (рядом с «Настроить под кабель»),
        # здесь остаётся только статус
        self.bridge_info = self._lbl(bridge_btns, "", 10, DIM)
        self.bridge_info.pack(side="left", padx=(10, 0))

        self.mic_status = self._lbl(self.tab_mic, "", 10, DIM)
        self.mic_status.pack(anchor="w", padx=16, pady=(4, 6))

        guide = tk.LabelFrame(self.tab_mic, text=" Как слышат другие ", bg=BG, fg=DIM,
                              font=("Segoe UI", 9), padx=14, pady=10)
        guide.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        guide_text = (
            "Если мост не подходит, есть ещё варианты:\n"
            "  • Ресурс на сервере (вкладка «В игру») — фразу играет сервер,\n"
            "    микрофон вообще не затрагивается, ничего ставить не надо.\n"
            "  • Stereo Mix без моста: играем в устройство, которое он захватывает;\n"
            "    свою речь туда же — mmsys.cpl -> Запись -> микрофон -> Свойства ->\n"
            "    «Прослушивать это устройство» -> вывод Realtek USB Audio.\n"
            "  • VoiceMeeter/VB-CABLE — если реплики должны идти именно голосом,\n"
            "    а микрофон остался чистым.\n"
        )
        self._lbl(guide, guide_text, 10, FG).pack(anchor="w")

    def _load_devices(self) -> None:
        try:
            inputs, outputs = hk.list_devices()
        except Exception as exc:  # noqa: BLE001
            self.mic_status.config(text=f"Аудиоустройства: {exc}")
            return
        cur_in, cur_out = hk.default_devices()

        outs = outputs
        virtual = [o for o in outs if hk.is_virtual_cable(o[1])]
        if virtual:
            outs = virtual + [o for o in outs if o not in virtual]
        self._out_list = outs
        self.out_combo["values"] = [f"{i}: {n}" for i, n in outs]
        # В списке микрофонов только реальные: без обобщённых драйверов и Stereo Mix
        mic_inputs = [(i, n) for i, n in inputs
                      if not hk.is_stereo_mix(n)
                      and not any(g in n.lower() for g in
                                  ("первичный драйвер", "primary sound capture",
                                   "переназначение звуковых устр"))]
        pool = mic_inputs or inputs
        self._in_list = pool
        self.in_combo["values"] = [f"{i}: {n}" for i, n in pool]
        # выбор устройства вывода
        if outs:
            pick = next((i for i, n in outs if i == cur_out), outs[0][0])
            self.out_device = pick
            for idx, (i, _n) in enumerate(outs):
                if i == pick:
                    self.out_combo.current(idx)
                    break
        # выбор микрофона (в том же порядке, что и значения combobox)
        if pool:
            rec_i, _rec_n = core.recalled_mic()
            pick_in = next((i for i, n in pool if i == cur_in), pool[0][0])
            if rec_i is not None and any(i == rec_i for i, _ in pool):
                pick_in = rec_i  # микрофон, с которого ты записывал
            self.in_device = pick_in
            for idx, (i, _n) in enumerate(pool):
                if i == pick_in:
                    self.in_combo.current(idx)
                    break
        if not hasattr(self, "_device_binds_done"):
            self.out_combo.bind("<<ComboboxSelected>>", self._on_out_change)
            self.in_combo.bind("<<ComboboxSelected>>", self._on_in_change)
            self._device_binds_done = True

        # Режим без виртуального кабеля: встроенный в Windows Stereo Mix
        mix_idx, mix_name = hk.find_stereo_mix(inputs)
        render_idx, render_name = hk.find_render_for_capture(inputs, outputs)
        self.stereo_mix = (mix_idx, mix_name, render_idx, render_name)
        if mix_idx is not None:
            self._btn(self.tab_mic, "◎ Режим без установки (Stereo Mix)",
                       self._use_stereo_mix, "#1e6f3f", "#fff", 10, 14, 8).pack(
                side="left", padx=(8, 0))
            self.mic_status.config(
                text=f"Найден встроенный Stereo Mix: «{mix_name}» — можно обойтись без установки.")
        elif virtual:
            self.mic_status.config(text="Найдены виртуальные кабели — они в списке первыми.")
        else:
            self.mic_status.config(
                text="Stereo Mix не найден: без него нужен виртуальный кабель "
                     "(VoiceMeeter / VB-CABLE).")

    def _auto_route(self) -> tuple[bool, str]:
        """Авто-настройка маршрута под виртуальный кабель или Stereo Mix.

        Работает в обоих интерфейсах (старый и новый) — не трогает виджеты,
        только состояние Studio и LiveTab. Возвращает (ok, сообщение).

        Порядок:
          1. выход = «CABLE Input» (если кабель установлен), иначе Stereo Mix;
          2. микрофон = реальный (без служебных и кабельных);
          3. мост включается;
          4. сообщаем, какой микрофон выбрать в игре.
        """
        devs = {}
        try:
            import cable as cable_mod
            devs = cable_mod.cable_devices()
        except Exception:
            devs = {}

        try:
            inputs, outputs = hk.list_devices()
        except Exception as exc:  # noqa: BLE001
            return False, f"аудиоустройства: {exc}"

        capture_name = ""
        if devs.get("output"):
            render_idx, render_name = devs["output"]
            capture_name = devs.get("input", (0, "CABLE Output"))[1]
        else:
            mix_idx, mix_name = hk.find_stereo_mix(inputs)
            if mix_idx is None:
                return False, ("нет ни виртуального кабеля, ни Stereo Mix — "
                               "установи VB-CABLE отдельно (vb-audio.com)")
            render_idx, render_name = hk.find_render_for_capture(inputs, outputs)
            capture_name = mix_name
            if render_idx is None:
                return False, "не нашёл устройство вывода под Stereo Mix"

        # 1. выход
        self.out_device = render_idx
        live = getattr(self, "live", None)
        if live is not None:
            try:
                live.set_out_device(render_idx)
            except Exception:
                pass

        # 2. микрофон — реальный
        skip = ("стерео микшер", "stereo mix", "первичный драйвер",
                "primary sound capture", "переназначение звуковых",
                "cable output", "vb-audio")
        for i, n in inputs:
            if any(g in n.lower() for g in skip):
                continue
            self.in_device = i
            if live is not None:
                try:
                    live.set_mic_device(i)
                except Exception:
                    pass
            break

        # 3. мост
        if self.bridge is not None and getattr(self.bridge, "running", False):
            self.bridge.stop()
            self.bridge = None
        ok, msg = self._start_bridge()
        if not ok:
            return False, msg
        return True, (f"Готово: играем в «{render_name}». "
                      f"В Discord/игре выбери микрофоном «{capture_name}».")

    def _use_stereo_mix(self) -> None:
        """Режим без установки: играем в устройство, которое захватывает Stereo Mix."""
        mix_idx, mix_name, render_idx, render_name = getattr(
            self, "stereo_mix", (None, "", None, ""))
        if mix_idx is None:
            self.mic_status.config(text="Stereo Mix в системе не найден")
            return
        self.in_device = mix_idx
        for idx, value in enumerate(self.in_combo["values"]):
            if value.startswith(f"{mix_idx}:"):
                self.in_combo.current(idx)
                break
        if render_idx is not None:
            self.out_device = render_idx
            for idx, value in enumerate(self.out_combo["values"]):
                if value.startswith(f"{render_idx}:"):
                    self.out_combo.current(idx)
                    break
        self.mic_status.config(
            text=f"Режим без установки: играем в «{render_name or 'устройство вывода'}», "
                 f"в игре микрофон = «{mix_name}». Проверь кнопкой «Проверить маршрут».")

    def _diag_devices(self) -> None:
        """Показать реальное состояние аудиоустройств."""
        import audiodev
        import sounddevice as sd

        self.mic_status.config(text="Проверяю устройства...")
        self.root.update()
        lines = []

        try:
            devices = sd.query_devices()
        except Exception as exc:  # noqa: BLE001
            self.mic_status.config(text=f"Устройства: {exc}")
            return

        for kind, label in (("input", "ВХОД"), ("output", "ВЫХОД")):
            lines.append(f"--- {label} ---")
            seen = set()
            for i, d in enumerate(devices):
                if kind == "input" and d["max_input_channels"] <= 0:
                    continue
                if kind == "output" and d["max_output_channels"] <= 0:
                    continue
                key = d["name"].split("(")[0].strip()
                if key in seen:
                    continue
                seen.add(key)
                rates = audiodev.working_rates(i, kind)
                if rates:
                    lines.append(f"  {d['name'][:38]:<40} ок: {rates[0]} Гц")
                else:
                    lines.append(f"  {d['name'][:38]:<40} НЕ ОТКРЫВАЕТСЯ")

        loop = [(i, d["name"]) for i, d in enumerate(devices)
                if d["max_input_channels"] > 0
                and any(k in d["name"].lower() for k in
                        ("стерео микшер", "stereo mix", "loopback"))]
        lines.append("")
        if loop:
            lines.append("Перехват системного звука (loopback):")
            for i, n in loop:
                rates = audiodev.working_rates(i, "input")
                lines.append(f"  {n[:44]:<46} {rates[0] if rates else 'не работает'} Гц")
            lines.append("Но RedM/Mumble обычно НЕ показывает его в списке микрофонов.")
        else:
            lines.append("Loopback-устройств в системе нет — для маршрута в микрофон "
                         "нужен виртуальный кабель.")

        text = "\n".join(lines)
        panel = getattr(self, "task_panel", None)
        if panel is not None:
            panel.begin("Диагностика аудиоустройств", ["Проверка входов", "Проверка выходов",
                                                       "Поиск loopback"], 3)
            panel.step(0, "done")
            panel.step(1, "done")
            panel.step(2, "done", "итог в журнале")
            for line in lines:
                panel.log("dim" if line.startswith("---") else "", line)
            panel.finish(True)
        self.mic_status.config(text="Диагностика — в журнале")

    def _install_cable(self) -> None:
        """Установить виртуальный аудиокабель (VB-CABLE).

        Раньше просто открывался сайт vb-audio.com — но с этой машины он
        недоступен (таймаут), и установка не получалась. Теперь установщик
        качается автоматически с доступного зеркала и запускается.
        """
        import cable

        self.mic_status.config(text="ставлю виртуальный кабель…")
        devs = cable.cable_devices()
        if devs:
            self.mic_status.config(
                text=f"Кабель уже установлен: {devs.get('output', (0, ''))[1]}")
            self._load_devices()
            return

        def work():
            ok, msg = cable.download(
                progress=lambda s: self.log_queue.put(f"[мост] {s}"))
            if not ok:
                self.log_queue.put(f"[мост] {msg}")
                return
            ok2, msg2 = cable.run_installer()
            self.log_queue.put(f"[мост] {msg2}")

        threading.Thread(target=work, daemon=True).start()

    def _check_cable(self) -> None:
        """Проверить, появились ли устройства кабеля после установки."""
        import cable
        devs = cable.cable_devices()
        if not devs:
            self.mic_status.config(
                text="Кабель не найден. Нажми «Установить мост» и в окне "
                     "установщика нажми «Install Driver».")
            return
        self._load_devices()
        out_name = devs.get("output", (0, "?"))[1]
        in_name = devs.get("input", (0, "?"))[1]
        self.mic_status.config(
            text=f"Кабель есть: играй в «{in_name}», а микрофон в игре "
                 f"выбери «{out_name}».")
        # сразу подставляем устройство вывода
        try:
            for idx, (i, _n) in enumerate(self._out_list):
                if i == devs.get("output", (None, ""))[0]:
                    self.out_combo.current(idx)
                    self.out_device = i
                    break
        except Exception:
            pass

    def _on_out_change(self, _event=None) -> None:
        value = self.out_combo.get()
        if value:
            self.out_device = int(value.split(":")[0])

    def _on_in_change(self, _event=None) -> None:
        value = self.in_combo.get()
        if value:
            self.in_device = int(value.split(":")[0])

    def _route_test(self) -> None:
        sel = ()
        try:
            sel = self.phrase_tree.selection()
        except Exception:
            pass
        path = None
        if sel:
            try:
                idx = self.phrase_tree.index(sel[0])
                path = self._phrase_path(self.phrases[idx]["id"])
            except Exception:
                path = None
        if not path or not os.path.exists(path):
            path = os.path.join(sp.output_paths()["out_mp3"], "mx_01.mp3")
        if not os.path.exists(path):
            self.mic_status.config(text="Нет озвучки — сначала запиши фразы")
            return
        try:
            hk.play_file(path, self.out_device, self._volume())
            self.mic_status.config(text="Играю в выбранное устройство — проверь микрофон")
        except Exception as exc:  # noqa: BLE001
            self.mic_status.config(text=f"Ошибка: {exc}")

    def _volume(self) -> float:
        """Громкость проигрывания: 0..1.5. В новом UI vol_var не создаётся."""
        try:
            return float(self.vol_var.get())
        except Exception:
            return 1.0

    def _measure_route(self) -> None:
        self.mic_status.config(text="Измеряю микрофон…")

        def _work():
            res = hk.measure_input(self.in_device, 3.0)
            self.root.after(0, lambda: self.mic_status.config(
                text=f"Микрофон: пик {res['peak']:.3f}, RMS {res['rms']:.4f} — {res['verdict']}"))

        threading.Thread(target=_work, daemon=True).start()

    def _toggle_hotkeys(self) -> None:
        """Глобальные хоткеи для ФРАЗ (вкладка «Микрофон»).

        Хоткеи живого перевода живут отдельно (префикс "live:"), чтобы
        включение/выключение здесь не сносило их.
        """
        if self.hotkey_enabled:
            self.hotkeys.unregister_prefix("phrase:")
            self.hotkey_enabled = False
            self.hk_btn.config(text="⌨ Включить глобальные хоткеи", bg="#2c313a", fg=FG)
            self.mic_status.config(text="Глобальные хоткеи фраз выключены")
            return
        self.hotkeys.unregister_prefix("phrase:")
        ok = 0
        for phrase in self.phrases:
            key = phrase.get("hotkey", "")
            if key and self.hotkeys.register(key, f"phrase:{phrase['id']}"):
                ok += 1
        self.hotkeys.start()
        self.hotkey_enabled = True
        self.hk_btn.config(text="⌨ Выключить глобальные хоткеи", bg="#c0392b", fg="#fff")
        self.mic_status.config(
            text=f"Хоткеи фраз включены ({ok}): Ctrl+Alt+<клавиша>. Работают, когда игра в фокусе.")

    def _on_hotkey(self, action: str) -> None:
        """Глобальный хоткей.

        ВАЖНО: вызывается из потока-читателя WM_HOTKEY. Tkinter можно
        трогать ТОЛЬКО из главного потока, а `root.after` из чужого потока
        ненадёжен (RuntimeError «main thread is not in main loop» — именно
        он глушился и выглядел как «хоткей не работает»).

        Поэтому: только кладём действие в очередь. Разбирает её главный
        поток в _poll_live (раз в 30 мс).
        """
        self._hk_queue.put(action)

    def _drain_hotkeys(self) -> None:
        """Разобрать очередь хоткеев (главный поток)."""
        while True:
            try:
                action = self._hk_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._do_hotkey(action)
            except Exception as exc:  # noqa: BLE001
                print(f"hotkey {action}: {type(exc).__name__}: {exc}")

    def _log_hotkey(self, action: str) -> None:
        """Записать сработавший хоткей в файл.

        В EXE нет консоли, а окна-сообщения тоже нет — единственный способ
        убедиться, что хоткей дошёл до интерфейса, это журнал.
        """
        try:
            logs = os.path.join(sp.workspace(), "logs")
            os.makedirs(logs, exist_ok=True)
            with open(os.path.join(logs, "hotkey_events.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {action}\n")
                fh.flush()
        except Exception:
            pass

    def _do_hotkey(self, action: str) -> None:
        """Собственно действие по хоткею (уже в главном потоке)."""
        self._log_hotkey(action)
        # хоткеи живого перевода имеют префикс "live:"
        if action.startswith("live:"):
            live = getattr(self, "live", None)
            if live is not None:
                live.on_hotkey(action)
            return
        # хоткеи фраз: "phrase:<id>"
        phrase_id = action.split(":", 1)[1] if action.startswith("phrase:") else action
        for phrase in self.phrases:
            if phrase["id"] == phrase_id:
                path = self._phrase_path(phrase_id)
                if os.path.exists(path):
                    if self.bridge is not None and self.bridge.running:
                        self.bridge.play_phrase(path)
                    else:
                        try:
                            hk.play_file(path, self.out_device, self._volume())
                        except Exception:
                            pass
                return

    # ---------- 4. Проверка ----------
    def _build_check(self) -> None:
        btns = tk.Frame(self.tab_check, bg=BG)
        btns.pack(anchor="w", padx=16, pady=(12, 6))
        self._btn(btns, "Разборчивость", self._check_quality).pack(side="left", padx=(0, 8))
        self._btn(btns, "Схожесть голоса", self._check_sim).pack(side="left", padx=(0, 8))
        self._btn(btns, "Правила проекта", self._check_rules).pack(side="left", padx=(0, 8))
        self._btn(btns, "Синхронность файлов", self._check_sync).pack(side="left")
        self.check_status = self._lbl(self.tab_check, "", 10, DIM)
        self.check_status.pack(anchor="w", padx=16, pady=(2, 4))
        self.check_panel = logpanel.LogPanel(self.tab_check, height_steps=4, height_log=16)
        self.check_panel.pack(fill="both", expand=True, padx=16, pady=(4, 12))

    def _check_run(self, title: str, job) -> None:
        self.check_status.config(text=title)
        self.check_panel.clear()

        def _worker():
            def cb(line: str) -> None:
                self.check_panel.log("dim", line)
            job(cb)

        threading.Thread(target=_worker, daemon=True).start()

    def _check_quality(self) -> None:
        self._check_run("Проверяю разборчивость…", core.verify_quality)

    def _check_sim(self) -> None:
        ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.check_status.config(text="Нет образца голоса")
            return
        self._check_run("Считаю схожесть голоса…", lambda cb: core.verify_similarity(ref, cb))

    def _check_rules(self) -> None:
        self._check_run("Проверяю правила проекта…", core.verify_rules)

    def _check_sync(self) -> None:
        self._check_run("Проверяю синхронность…", core.verify_sync)

    # ---------- 5. В игру ----------
    def _build_game(self) -> None:
        self._lbl(self.tab_game, "Куда положить файлы, чтобы реплики заработали в игре.",
                  11).pack(anchor="w", padx=16, pady=(12, 4))
        frame = tk.LabelFrame(self.tab_game, text=" Пути ", bg=BG, fg=DIM,
                              font=("Segoe UI", 9), padx=14, pady=10)
        frame.pack(fill="x", padx=16, pady=6)
        p = sp.output_paths()
        for label, value in (("Ресурс (ogg -> sounds/)", p["sounds"]),
                             ("Плеер (mp3 -> player/mp3/)", p["player_mp3"]),
                             ("Мастера (wav/ogg/mp3)", p["out_wav"].rsplit(os.sep, 1)[0]),
                             ("Образец голоса", p["reference"]),
                             ("Записи подсказок", p["samples"])):
            row = tk.Frame(frame, bg=BG)
            row.pack(fill="x", pady=2)
            self._lbl(row, label + ":", 9, DIM).pack(side="left")
            self._lbl(row, value, 9, ACCENT).pack(side="left", padx=(8, 0))

        steps = tk.LabelFrame(self.tab_game, text=" ", bg=BG, fg=DIM,
                              font=("Segoe UI", 9), padx=14, pady=10)
        steps.pack(fill="both", expand=True, padx=16, pady=(6, 6))
        text = (
            "ПУТЬ 1 (рекомендуемый) — фразы играет СЕРВЕР, микрофон не трогаем:\n"
            "   1. Нажми «Собрать ресурс для сервера» (кнопка ниже).\n"
            "   2. Скопируй папку server_resource в resources/ сервера RedZ.\n"
            "   3. В server.cfg:  ensure redz_mx_soundboard\n"
            "   4. В игре жми 1-9 / Numpad / F1-F12 — фразу слышат все игроки,\n"
            "      а твоя обычная речь идёт через микрофон как обычно.\n\n"
            "ПУТЬ 2 — встроенный Stereo Mix, тоже без установки чего-либо:\n"
            "   1. На вкладке «Микрофон» жми «Режим без установки (Stereo Mix)».\n"
            "   2. В игре выбери микрофоном «Стерео микшер (Realtek USB Audio)».\n"
            "   3. Свою речь направь туда же: Win+R -> mmsys.cpl -> вкладка\n"
            "      «Запись» -> свой микрофон -> «Свойства» -> «Прослушать это\n"
            "      устройство» -> устройство вывода: «Наушники/Динамики (Realtek\n"
            "      USB Audio)». Громкость прослушивания убавь, чтобы не было эха.\n"
            "   4. Проверь кнопкой «Проверить маршрут» — RMS должен быть больше нуля.\n\n"
            "ПУТЬ 3 — классика (VoiceMeeter/VB-CABLE): нужен, если хочешь, чтобы\n"
            "реплики шли именно голосом в голосовом канале.\n\n"
            "Важно: п.2.1 правил RedZ запрещает сторонний софт — путь 1 (серверный)\n"
            "не требует ничего стороннего."
        )
        self._lbl(steps, text, 10, FG).pack(anchor="w")

        btns = tk.Frame(self.tab_game, bg=BG)
        btns.pack(anchor="w", padx=16, pady=(0, 6))
        self._btn(btns, "Собрать ресурс для сервера", self._export_resource,
                  "#1e6f3f", "#fff", 10, 14, 8).pack(side="left", padx=(0, 8))
        self._btn(btns, "Разложить по папкам (ogg -> sounds, mp3 -> player)",
                  self._do_distribute).pack(side="left")
        self.game_status = self._lbl(self.tab_game, "", 10, ACCENT)
        self.game_status.pack(anchor="w", padx=16, pady=(0, 12))

    def _export_resource(self) -> None:
        try:
            path = core.export_server_resource()
        except Exception as exc:  # noqa: BLE001
            self.game_status.config(text=f"Не собралось: {exc}")
            return
        self.game_status.config(
            text=f"Ресурс готов: {path}\nСкопируй её в resources/ сервера и добавь "
                 f"в server.cfg: ensure redz_mx_soundboard")

    def _do_distribute(self) -> None:
        moved = core.distribute()
        self.phrase_status.config(
            text=f"Разложено: {moved['ogg']} ogg в sounds/, {moved['mp3']} mp3 в player/mp3/")

    # ---------- служебное ----------
    def _run_job(self, title: str, job, status=None, total: int = 0,
                 steps: list[str] | None = None, panel=None) -> None:
        """Запустить задачу с видимыми этапами."""
        if self.busy:
            msg = "Занято — дождись окончания текущей задачи"
            (status or self.phrase_status).config(text=msg)
            (panel or getattr(self, "task_panel", None)) and (panel or self.task_panel).log("warn", msg)
            return
        self.busy = True
        target = status or self.phrase_status
        target.config(text=title)
        panel = panel or getattr(self, "task_panel", None)
        self._current_panel = panel
        self._job_total = total
        self._job_title = title
        self._job_started = time.time()
        self._last_line_at = time.time()
        self._done_ids = []
        self._job_phrase_ids = list(getattr(self, "_job_phrase_ids", []))
        # вывод движка с прошлой задачи не должен влиять на новую
        self._engine_lines = []
        if panel is not None:
            panel.begin(title, steps or ["Выполнение"], total)

        def _worker():
            def cb(line: str) -> None:
                self.log_queue.put(line)

            code, error = -1, ""
            try:
                code = job(cb)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                self.log_queue.put(f"ОШИБКА ЗАДАЧИ: {error}")
                # полный трейсбек в файл: в EXE консоли нет, а обрезанного
                # текста "Permission denied" недостаточно, чтобы найти файл
                try:
                    import traceback
                    logs = os.path.join(sp.workspace(), "logs")
                    os.makedirs(logs, exist_ok=True)
                    stamp = time.strftime("%Y%m%d-%H%M%S")
                    path = os.path.join(logs, f"error_{stamp}.txt")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(f"Задача: {title}\n")
                        fh.write(f"Ошибка: {error}\n\n")
                        traceback.print_exc(file=fh)
                    self.log_queue.put(f"Подробности: {path}")
                except Exception:
                    pass
            finally:
                # busy сбрасываем ВСЕГДА, иначе кнопки навсегда «Занято»
                self.log_queue.put(f"=== завершено, код {code} ===")
                self.root.after(0, lambda: self._job_done(code, target, total, panel, error))

        threading.Thread(target=_worker, daemon=True).start()
        self._heartbeat()

    def _job_done(self, code: int, target, total: int = 0, panel=None,
                  error: str = "") -> None:
        self.busy = False
        ok = code == 0 and not error
        if error:
            target.config(text=f"Ошибка: {error[:80]}")
        elif ok:
            target.config(text="Готово")
        else:
            # Движок упал: показываем причину из его вывода, а не «код 1»
            reason = self._last_engine_error()
            if reason:
                target.config(text=f"Движок упал: {reason[:70]}")
            else:
                target.config(text=f"Завершилось с кодом {code}")
        panel = panel or getattr(self, "task_panel", None)
        if panel is not None:
            # закрываем шаги, которые остались невыполненными
            for i, st in enumerate(panel._steps):
                if st["status"] == "todo":
                    panel.step(i, "fail" if not ok else "done")
            panel.finish(ok, f"{total} фраз" if total else "")
        self._refresh_phrases()

    def _last_engine_error(self) -> str:
        """Последняя строка с ошибкой из вывода движка."""
        for line in reversed(getattr(self, "_engine_lines", [])):
            if re.match(r"^\w*(Error|Exception)\b", line.strip()):
                return line.strip()
        return ""

    def _drain_log(self) -> None:
        """Разбор вывода движка: шаги, прогресс и журнал."""
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if not line:
                continue
            self._handle_line(line)
        self.root.after(120, self._drain_log)

    def _handle_line(self, line: str) -> None:
        """Одна строка вывода движка -> обновление панели задачи."""
        self._last_line_at = time.time()
        # копия вывода движка: по ней ищем причину падения
        if not hasattr(self, "_engine_lines"):
            self._engine_lines = []
        self._engine_lines.append(line)
        if len(self._engine_lines) > 400:
            del self._engine_lines[:-400]
        panel = self._active_panel()
        if panel is None:
            return

        # прогресс генерации: «OK [07] 1.00 12.3s 1.87s Pinche cabron! | Pinche cabrón»
        m = re.match(r"^(OK|BAD|~)\s*\[(\d+)\]\s*([\d.]+)\s+([\d.]+)s\s+(.*?)(?:\s*\|\s*(.*))?$", line)
        if m:
            kind, lid, score, dur, text, heard = m.groups()
            done = int(lid)
            self._job_done_count = done
            panel.progress_set(done)
            if lid not in self._done_ids:
                self._done_ids.append(lid)
            panel.set_stage(1, f"{lid}: {text.strip()[:34]}")
            panel.step(2, "doing", "разборчивость проверяется по факту")
            panel.log("ok" if kind == "OK" else "bad", line)
            return

        if "Фраз из приложения" in line:
            panel.log("head", line)
            panel.step(0, "done", line.split(":")[-1].strip() + " фраз")
            panel.set_stage(1, "передача в движок")
            return
        if line.startswith("Модель загружена"):
            panel.log("head", line)
            panel.set_stage(1, "модель загружена")
            return
        if line.startswith("Проверка качества"):
            panel.log("dim", line)
            return
        if "Разборчиво" in line or "синхронно" in line or "Средняя схожесть" in line:
            panel.log("ok", line)
            return
        if "НАЙДЕНЫ" in line or line.startswith("BAD"):
            panel.log("bad", line)
            return
        # Трейсбек движка: показываем причину, а не обрывок
        if re.match(r"^\s*File \"|^\w*(Error|Exception)\b", line):
            panel.log("bad", line)
            return
        if line.startswith("==="):
            panel.log("dim", line)
            return
        panel.log("", line)

    def _active_panel(self):
        panel = getattr(self, "_current_panel", None)
        return panel

    def _refresh_engine(self) -> None:
        python = sp.engine_python()
        # в новом UI engine_lbl не создаётся — обновляем только если есть
        lbl = getattr(self, "engine_lbl", None)
        if lbl is not None:
            try:
                lbl.config(
                    text=("движок: готов" if python else "движок: НЕ УСТАНОВЛЕН"))
            except Exception:
                pass
        if self.root is not None:
            self.root.after(3000, self._refresh_engine)

    # ---------- управление жизненным циклом движка (новый UI) ----------

    def start_engine(self) -> tuple[bool, str]:
        """Запустить движок живого перевода и загрузить модели.

        Возвращает (ok, message). Не перезагружает, если уже READY.
        """
        live = getattr(self, "live", None)
        if live is None:
            return False, "LiveTab не инициализирован"
        translator = getattr(live, "translator", None)
        if translator is not None and translator.ready:
            self.engine_state = "READY"
            self.engine_error = ""
            return True, "движок уже готов"
        if translator is not None and translator.loading:
            self.engine_state = "LOADING"
            return True, "движок уже загружается…"
        if translator is not None and translator.busy:
            self.engine_state = "STOPPING"
            return False, "движок занят, подождите"
        # Проверяем наличие движка и образца голоса
        python = sp.engine_python()
        if not python or not os.path.exists(python):
            self.engine_state = "ERROR"
            self.engine_error = "движок не установлен (setup_env.ps1)"
            return False, self.engine_error
        ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.engine_state = "ERROR"
            self.engine_error = "нет образца голоса (запишите на вкладке «Голоса»)"
            return False, self.engine_error
        # Запускаем
        self.engine_state = "LOADING"
        self.engine_error = ""
        ok = live._ensure_engine()
        if ok:
            # Ожидаем готовности (модели грузятся ~15-30 с)
            # Готовность определяется через on_event("state", {"ready": True})
            # в LiveTab, которая обновит translator.ready
            return True, "движок запускается, загрузка моделей…"
        else:
            self.engine_state = "ERROR"
            self.engine_error = translator.error or "движок не запустился"
            return False, self.engine_error

    def stop_engine(self) -> tuple[bool, str]:
        """Остановить движок и освободить модели/VRAM.

        Возвращает (ok, message).
        """
        live = getattr(self, "live", None)
        if live is None:
            return False, "LiveTab не инициализирован"
        # Остановить захват входящего звука ПЕРЕД любой проверкой состояния
        # движка, чтобы захват не оставался активным при аварийном завершении
        # движка или когда движок ещё не был запущен.
        try:
            live.stop_capture()
        except Exception as exc:  # noqa: BLE001
            _diag(f"ошибка остановки захвата при остановке движка: {exc}")
        translator = getattr(live, "translator", None)
        if translator is None or not translator.ready and not translator.loading:
            self.engine_state = "STOPPED"
            self.engine_error = ""
            return True, "движок уже остановлен"
        # Не останавливаем посреди активной операции
        if translator.busy:
            return False, "движок занят операцией, дождитесь завершения"
        self.engine_state = "STOPPING"
        # Гасим всё, что могло бы ещё звучать: очередь воспроизведения в GUI,
        # поток перевода в мосту, флаги режимов.
        try:
            live._stop_translation()
        except Exception as exc:  # noqa: BLE001
            _diag(f"очистка перевода при остановке: {exc}")
        try:
            live._hold_on = False
            live._cont_on = False
            live._hold_wait_play = False
            live._swap_busy = False
            live._swap_wait_play = False
        except Exception:
            pass
        try:
            translator.stop()
        except Exception as exc:  # noqa: BLE001
            self.engine_state = "ERROR"
            self.engine_error = str(exc)
            return False, f"ошибка остановки: {exc}"
        # Даём движку время выгрузить модели (unload) до terminate,
        # иначе Windows освобождает RAM с задержкой в несколько ГБ.
        try:
            import gc
            for _ in range(3):
                gc.collect()
        except Exception:
            pass
        self.engine_state = "STOPPED"
        self.engine_error = ""
        return True, "движок остановлен, модели выгружены"

    def get_engine_status(self) -> dict:
        """Вернуть текущий статус движка для UI."""
        live = getattr(self, "live", None)
        translator = getattr(live, "translator", None) if live else None
        python = sp.engine_python()
        if translator is not None:
            if translator.ready:
                self.engine_state = "READY"
                self.engine_error = ""
            elif translator.loading:
                self.engine_state = "LOADING"
            elif translator.error:
                self.engine_state = "ERROR"
                self.engine_error = translator.error
        return {
            "state": self.engine_state,
            "error": self.engine_error,
            "engine_installed": python is not None and os.path.exists(python),
            "translator_ready": translator.ready if translator else False,
            "translator_loading": translator.loading if translator else False,
            "translator_busy": translator.busy if translator else False,
        }

    def _populate_devices_new_ui(self) -> None:
        """Заполнить списки аудиоустройств для нового UI.

        Вызывается после создания корневого окна (в main()).
        Аналог _load_devices() из старого UI, но без tkinter-виджетов
        (они создаются в SettingsPage и HomePage).
        """
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            inputs = [(i, d["name"]) for i, d in enumerate(devices)
                       if d["max_input_channels"] > 0]
            outputs = [(i, d["name"]) for i, d in enumerate(devices)
                        if d["max_output_channels"] > 0]
        except Exception:
            return
        mic_pool = [(i, n) for i, n in inputs
                    if not any(g in n.lower() for g in
                               ("стерео микшер", "stereo mix", "первичный драйвер",
                                "primary sound capture", "переназначение звуковых",
                                "cable output", "vb-audio"))]
        pool = mic_pool or inputs
        # Выбираем устройства по умолчанию
        try:
            cur_in = sd.default.device[0]
            cur_out = sd.default.device[1]
        except Exception:
            cur_in = cur_out = None
        if pool:
            rec_i, _rec_n = core.recalled_mic()
            pick_in = next((i for i, n in pool if i == cur_in), pool[0][0])
            if rec_i is not None and any(i == rec_i for i, _ in pool):
                pick_in = rec_i
            self.in_device = pick_in
        if outputs:
            pick_out = next((i for i, n in outputs if i == cur_out), outputs[0][0])
            self.out_device = pick_out

    def _on_close(self) -> None:
        self.hotkeys.unregister_all()
        # закрыть процесс оверлея, иначе он останется висеть поверх игры
        proc = getattr(self, "_overlay_proc", None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            self._overlay_proc = None
        try:
            self.recorder.stop()
        except Exception:
            pass
        if self.bridge is not None:
            try:
                self.bridge.stop()
            except Exception:
                pass
        # движок живого перевода — отдельный процесс, его надо остановить
        live = getattr(self, "live", None)
        if live is not None:
            # остановить захват входящего звука перед движком
            try:
                live.stop_capture()
            except Exception:
                pass
            try:
                if live.translator is not None:
                    live.translator.stop()
            except Exception:
                pass
            # запись звука игры (перехват игроков) тоже закрыть
            try:
                live._stop_peer()
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

    def select_tab(self, index: int) -> None:
        """Программно переключить вкладку (0..4) — для тестов и автопроверок."""
        if hasattr(self, "nb"):
            self.nb.select(index)
            self.nb.focus_force()


def _diag_voice_all() -> int:
    """Диагностический режим: прогнать задачу «Озвучить всё» и снять трейсбек.

    Запуск:  RedZVoiceStudio.exe --diag-voice-all
    Идёт РОВНО тем же путём, что и кнопка: Studio -> _voice_all -> _run_job
    -> рабочий поток. Ошибка пишется в workspace\\logs\\error_*.txt —
    в EXE нет консоли, поэтому иначе её не увидеть.
    """
    import traceback
    studio = Studio()
    out = os.path.join(sp.workspace(), "logs")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "diag_voice_all.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("=== диагностический запуск ===\n")
        fh.write(f"argv: {sys.argv}\n")
        fh.write(f"фраз: {len(studio.phrases)}\n")

    def finish() -> None:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"\nстатус: {studio.phrase_status.cget('text')}\n")
                fh.write(f"busy: {studio.busy}\n")
                try:
                    fh.write("журнал:\n" +
                             studio.task_panel.log_text.get("1.0", "end") + "\n")
                except Exception:
                    pass
        except Exception:
            pass
        studio.root.quit()

    def go() -> None:
        try:
            studio._voice_all()
        except Exception:  # noqa: BLE001
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\nИСКЛЮЧЕНИЕ ПРИ СТАРТЕ:\n" + traceback.format_exc())
            finish()
            return
        # ждём завершения задачи (или 8 минут)
        deadline = time.time() + 480
        def poll() -> None:
            if not studio.busy or time.time() > deadline:
                finish()
                return
            studio.root.after(500, poll)
        studio.root.after(500, poll)

    studio.root.withdraw()
    studio.root.after(800, go)
    studio.root.mainloop()
    return 0


def _diag_live() -> int:
    """Диагностика живой перевода в EXE: прогнать запись и написать отчёт.

    Запуск:  RedZVoiceStudio.exe --diag-live
    Результат: workspace\\logs\\diag_live.txt
    """
    import time
    studio = Studio()
    live = studio.live
    logs = os.path.join(sp.workspace(), "logs")
    os.makedirs(logs, exist_ok=True)
    path = os.path.join(logs, "diag_live.txt")

    def write(text: str) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
            fh.flush()

    write(f"=== диагностика живого перевода {time.strftime('%H:%M:%S')} ===")
    # списки устройств и записей заполняются по таймеру — для диагностики
    # заполняем сразу, иначе они пустые
    live._refresh_devices()
    live._refresh_samples()
    write(f"микрофон: {live.mic_combo.get()}")
    write(f"вывод:    {live.out_combo.get()}")
    write(f"записей:  {len(live._sample_files)}")

    def step1():
        live._test_with_sample()
        write("запущен перевод записи…")

    def step2():
        if live._last_es:
            write(f"статус: {live.state_lbl.cget('text')}")
            write(f"RU: {live._last_ru}")
            write(f"ES: {live._last_es}")
            write("ИТОГ: ок")
            studio.root.quit()
            return
        if time.time() > deadline:
            write(f"статус: {live.state_lbl.cget('text')}")
            write(f"RU: {live._last_ru}")
            write(f"ES: {live._last_es}")
            write("ИТОГ: не сработало")
            studio.root.quit()
            return
        studio.root.after(500, step2)

    deadline = time.time() + 240
    studio.root.after(600, step1)
    studio.root.after(1500, step2)
    studio.root.mainloop()
    try:
        if live.translator:
            live.translator.stop()
    except Exception:
        pass
    return 0


_CURRENT_STUDIO = None


def _install_crash_handlers() -> None:
    """Записывать необработанные исключения в logs/gui_crash.log.

    В собранном EXE нет консоли, поэтому без этого любое падение выглядит
    как «тихий краш». Пишем и стек, и текущий поток.
    """
    import traceback

    def _log_crash(text: str) -> None:
        try:
            logs = os.path.join(sp.workspace(), "logs")
            os.makedirs(logs, exist_ok=True)
            path = os.path.join(logs, "gui_crash.log")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} "
                         f"thread={threading.current_thread().name} =====\n")
                fh.write(text)
                fh.flush()
        except Exception:
            pass

    def _exc_hook(exc_type, exc, tb):
        _log_crash("".join(traceback.format_exception(exc_type, exc, tb)))
        # Печатаем и в stderr — на случай запуска из исходников
        traceback.print_exception(exc_type, exc, tb)

    def _thread_hook(args):
        _log_crash("".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback)))

    try:
        sys.excepthook = _exc_hook
    except Exception:
        pass
    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass


def main() -> None:
    global _CURRENT_STUDIO
    # Диагностика крашей: любое необработанное исключение (в главном потоке
    # или в потоке) пишем в logs/gui_crash.log — иначе в EXE без консоли
    # причина падения теряется безвозвратно.
    _install_crash_handlers()
    # маркер запуска: в EXE нет консоли, поэтому пишем в файл
    try:
        _marks = os.path.join(sp.workspace(), "logs")
        os.makedirs(_marks, exist_ok=True)
        with open(os.path.join(_marks, "startup.txt"), "a", encoding="utf-8") as fh:
            fh.write(f"запуск: {sys.argv}\n")
    except Exception:
        pass
    # Обновляем рабочие копии инструментов ДО всего остального: движок и
    # клонер запускаются отдельным процессом и читают файлы из рабочей
    # папки. Если обновлять их только при старте движка, то после
    # обновления EXE пользователь до запуска движка работал на старой
    # версии скриптов (и правки не были видны).
    try:
        sp.workspace_tools()
    except Exception as exc:  # noqa: BLE001
        try:
            with open(os.path.join(sp.workspace(), "logs", "tools_update.log"),
                      "a", encoding="utf-8") as fh:
                fh.write(f"ошибка обновления инструментов: {exc}\n")
        except Exception:
            pass
    # два экземпляра делят рабочую папку -> PermissionError и порча файлов
    if not sp.single_instance_lock():
        try:
            import tkinter.messagebox as mb
            mb.showwarning(
                "RedZ Voice Studio",
                "Приложение уже запущено.\n"
                "Два экземпляра не могут работать с одной рабочей папкой — "
                "закрой предыдущий и открой снова.")
        except Exception:
            pass
        return
    if "--diag-voice-all" in sys.argv:
        _diag_voice_all()
        return
    if "--diag-live" in sys.argv:
        _diag_live()
        return
    if "--enable-hotkeys" in sys.argv:
        # автозапуск глобальных хоткеев (для автотеста и для тех,
        # кто не хочет нажимать кнопку каждый раз)
        studio = Studio()
        studio.root.after(1500, lambda: studio.live._toggle_hotkeys())
        studio.run()
        return
    if "--tab" in sys.argv:
        # открыть сразу нужную вкладку (0..5) — для проверки и скриншотов
        try:
            idx = int(sys.argv[sys.argv.index("--tab") + 1])
        except Exception:
            idx = 0
        studio = Studio()
        studio.root.after(700, lambda: studio.select_tab(idx))
        studio.run()
        return

    # Выбор интерфейса: по умолчанию Qt (если PySide6 есть в сборке),
    # --ui old — старый Tk, --ui new — новый Tk.
    try:
        import PySide6  # noqa: F401
        ui_mode = "qt"
    except Exception:
        ui_mode = "new"
    for arg in sys.argv:
        if arg == "--ui-old":
            ui_mode = "old"
            break
        if arg == "--ui-new":
            ui_mode = "new"
            break
        if arg == "--ui-qt":
            ui_mode = "qt"
            break

    if ui_mode == "old":
        # Старый интерфейс (6 вкладок через ttk.Notebook)
        Studio().run()
        return

    if ui_mode == "qt":
        # Qt-интерфейс (PySide6 + QML) — отдельное приложение,
        # не использует Tkinter.
        from qtapp.main import main as qt_main
        sys.exit(qt_main())
        return

    # Новый интерфейс (3 раздела: Главная / Голоса / Настройки)
    # MainWindow создаёт ЕДИНЫЙ tk.Tk() — Studio использует его же,
    # чтобы не было двух окон.
    import tkinter as _tk
    from ui.main_window import MainWindow
    from ui.splash import SplashScreen

    # Заставка с прогрессом: инициализация занимает ~1 с, и без неё
    # пользователь видит белый экран / «программа не отвечает».
    splash = SplashScreen()

    splash.step("Подготовка рабочей папки…", 8)
    studio = Studio(use_new_ui=True, root=None)

    splash.step("Создание окна…", 18)
    app = MainWindow(studio)
    studio.root = app.root  # общий корень — MainWindow владеет окном

    splash.step("Подключение интерфейса…", 62)
    # Связываем боковую панель с Studio, чтобы live_tab мог добавлять
    # записи в историю при получении переводов.
    studio.sidebar = app.sidebar
    # Создаём tk-переменные, которые требовали корневого окна
    studio.lang = tk.StringVar(value="ru")

    splash.step("Запуск живого перевода…", 78)
    # Создаём placeholder-вкладку для LiveTab (её UI не показывается,
    # но логика LiveTab — перевод, захват, входящий TTS — работает)
    studio.tab_live = _tk.Frame(app.root, bg=BG)
    studio._build_live()

    splash.step("Поиск аудиоустройств…", 90)
    # Заполняем списки аудиоустройств для нового UI
    studio._populate_devices_new_ui()

    splash.step("Финальная проверка…", 97)
    _CURRENT_STUDIO = studio

    splash.step("Готово", 100)
    splash.close()
    # LiveTab опросит устройства через 300 мс — обновляем UI после этого
    def _refresh_ui_devices():
        try:
            app.home._refresh_devices()
            app.settings._refresh_devices()
        except Exception:
            pass
    app.root.after(600, _refresh_ui_devices)
    # Перепланируем отложенные вызовы Studio на общий корень
    app.root.after(120, studio._drain_log)
    app.root.after(100, studio._poll_live)
    app.root.after(30, studio._poll_hotkeys)
    # Хоткеи живого перевода включаем СРАЗУ: пользователь не должен
    # ничего настраивать — приложение запустилось, значит работает.
    app.root.after(900, _enable_live_hotkeys)
    # Виртуальный кабель подключаем автоматически: если он установлен,
    # мост поднимается сам (в игре сразу выбирают «CABLE Output»).
    app.root.after(1500, _auto_enable_cable)
    app.run()


def _enable_live_hotkeys() -> None:
    """Включить глобальные хоткеи живого перевода при старте."""
    try:
        studio = _CURRENT_STUDIO
        live = getattr(studio, "live", None) if studio else None
        if live is None or getattr(live, "hotkeys_on", False):
            return
        live._toggle_hotkeys()
    except Exception as exc:  # noqa: BLE001
        _diag(f"автохоткеи не удались: {exc}")


def _diag(text: str) -> None:
    """Записать диагностическую строку (в лог движка, как LiveTab)."""
    try:
        logs = os.path.join(sp.workspace(), "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "live_engine.log"), "a",
                  encoding="utf-8") as fh:
            fh.write(f"[gui] {text}\n")
    except Exception:
        pass


def _auto_enable_cable() -> None:
    """Поднять мост на виртуальный кабель, если он установлен.

    Пользователь не должен ничего нажимать: приложение запустилось —
    значит маршрут уже настроен. Если кабеля нет, тихо выходим.
    """
    try:
        studio = _CURRENT_STUDIO
        if studio is None:
            return
        if getattr(studio, "bridge", None) is not None and \
                getattr(studio.bridge, "running", False):
            return
        ok, msg = studio._auto_route()
        _diag(f"автокабель: {msg}" if ok else f"автокабель: {msg}")
    except Exception as exc:  # noqa: BLE001
        _diag(f"автокабель не удался: {exc}")


if __name__ == "__main__":
    main()
