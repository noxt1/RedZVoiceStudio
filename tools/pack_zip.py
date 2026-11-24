"""Сборка архива проекта (обход блокировки EXE).

Compress-Archive падает с PermissionDenied, если запущенный экземпляр
удерживает файл. Здесь файл читается целиком с разрешением на чтение
и запись архива идёт из памяти.

    python tools\\pack_zip.py [путь-архива]
"""

from __future__ import annotations

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"build", "build_new", "dist_new", ".ecapa", "__pycache__", ".git"}
SKIP_FILES = {".gitignore"}


def read_bytes(path: str) -> bytes:
    """Прочитать файл, даже если его держит другой процесс."""
    with open(path, "rb") as fh:
        return fh.read()


def collect(base: str) -> list[tuple[str, str]]:
    items = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES or name.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base)
            items.append((full, rel))
    return items


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(ROOT), os.path.basename(ROOT) + ".zip")
    items = collect(ROOT)
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, rel in items:
            try:
                data = read_bytes(full)
            except OSError as exc:
                print(f"  ! пропущен {rel}: {exc}")
                continue
            z.writestr(rel.replace(os.sep, "/"), data)
    print(f"архив: {out}  {os.path.getsize(out) / 1e6:.1f} МБ  файлов: {len(items)}")

    # проверка
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        has_exe = "dist/Auraloom.exe" in z.namelist()
        print("битых записей:", bad or "нет", "| EXE внутри:", has_exe)


if __name__ == "__main__":
    main()
