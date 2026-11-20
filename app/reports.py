"""Отчёт для поддержки одним файлом.

Что попадает в zip:
  * `report.txt` — версия, сборка EXE (размер + SHA-256), система, снимок
    диагностики из интерфейса;
  * `logs/*` — `live_engine.log`, `diagnostics.log`, `startup.txt`,
    `tools_update.log`, `gui_crash.log` (большие логи обрезаются до
    последних ~2 МБ — для разбора хватает);
  * `settings.json` — `ui_settings.json` (устройства, громкости, режим).

Чего в отчёте НЕТ: `history.jsonl` (все переводы), `voice_profiles/`,
`voice_samples/`, `reference.wav`, модели. Тексты распознанной речи всё
равно есть в `live_engine.log` — об этом сказано в интерфейсе.

Папка: `<workspace>\\reports\\auraloom-report-ГГГГММДД-ЧЧММСС.zip`.
"""

from __future__ import annotations

import hashlib
import os
import platform
import sys
import time
import zipfile

import branding
import studio_paths as sp

LOG_NAMES = ("live_engine.log", "diagnostics.log", "startup.txt",
             "tools_update.log", "gui_crash.log")
LOG_TAIL_BYTES = 2 * 1024 * 1024


def _sha256(path: str) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except Exception as exc:      # noqa: BLE001
        return f"нет данных: {exc}"


def _add_log(zf: zipfile.ZipFile, path: str, arcname: str) -> None:
    """Положить лог целиком или хвостом, если он разросся."""
    try:
        size = os.path.getsize(path)
        if size <= LOG_TAIL_BYTES:
            zf.write(path, arcname)
            return
        with open(path, "rb") as fh:
            fh.seek(-LOG_TAIL_BYTES, os.SEEK_END)
            data = fh.read()
        head = "... (лог обрезан, показан хвост) ...\n".encode("utf-8")
        zf.writestr(arcname, head + data)
    except Exception:
        pass


def build_report_text(diag_text: str = "") -> str:
    """Версия, сборка и система — то, что нельзя восстановить из логов."""
    exe = sys.executable if getattr(sys, "frozen", False) else ""
    lines = [
        f"Auraloom {branding.APP_VERSION}",
        f"собрано: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"EXE: {exe or 'запуск из исходников'}",
    ]
    if exe and os.path.exists(exe):
        lines.append(f"EXE размер: {os.path.getsize(exe)}")
        lines.append(f"EXE SHA-256: {_sha256(exe)}")
    lines += [
        f"Python: {sys.version.split()[0]}",
        f"ОС: {platform.platform()}",
        "",
        "--- диагностика ---",
        (diag_text or "нет снимка").strip(),
        "",
    ]
    return "\n".join(lines)


def collect(diag_text: str = "", workspace_dir: str | None = None) -> str:
    """Собрать zip и вернуть его путь."""
    workspace = workspace_dir or sp.workspace()
    out_dir = os.path.join(workspace, "reports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(
        out_dir, "auraloom-report-" + time.strftime("%Y%m%d-%H%M%S") + ".zip")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.txt", build_report_text(diag_text))
        logs = os.path.join(workspace, "logs")
        for name in LOG_NAMES:
            src = os.path.join(logs, name)
            if os.path.exists(src):
                _add_log(zf, src, "logs/" + name)
        settings = os.path.join(workspace, "ui_settings.json")
        if os.path.exists(settings):
            zf.write(settings, "settings.json")
    return path


def open_folder(path: str) -> None:
    """Открыть папку с отчётом в проводнике."""
    import subprocess
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if folder and os.path.isdir(folder):
        subprocess.Popen(["explorer", folder])
