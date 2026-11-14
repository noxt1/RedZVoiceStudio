"""Проверка зеркал установщика VB-CABLE / VoiceMeeter.

vb-audio.com с этой машины недоступен (TLS timeout), поэтому ищем,
где установщик лежит на доступном хосте:
  * GitHub-репозитории с зеркалом;
  * пакет chocolatey (nupkg) — какие URL он тянет.

    python tools\\check_cable_sources.py
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
import zipfile

UA = {"User-Agent": "RedZVoiceStudio/1.0"}
REPOS = [
    "kiritoGM5/VBCABLE_Driver_Pack45",
    "AlekseyMartynov/action-vbcable-win",
    "airob0t/VB-cable",
    "syams86/Virtual-Audio-Pipeline",
]


def get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check_repo(full: str) -> None:
    print(f"\n--- {full} ---")
    try:
        data = json.loads(get(f"https://api.github.com/repos/{full}/git/trees/HEAD?recursive=1"))
    except Exception as exc:
        print(f"  ошибка: {exc}")
        return
    tree = data.get("tree", [])
    files = [t for t in tree if t.get("type") == "blob"]
    big = sorted(files, key=lambda t: t.get("size", 0), reverse=True)[:8]
    for t in big:
        print(f"  {t.get('size', 0):>10} Б  {t['path']}")
    # ищем текстовые файлы со ссылками на скачивание
    for t in files:
        name = t["path"].lower()
        if not name.endswith((".yml", ".yaml", ".md", ".ps1", ".sh", ".txt")):
            continue
        if t.get("size", 0) > 200000:
            continue
        try:
            content = get(f"https://raw.githubusercontent.com/{full}/HEAD/{t['path']}").decode(
                "utf-8", "replace")
        except Exception:
            continue
        for line in content.splitlines():
            low = line.lower()
            if "vb-audio" in low or "vbcable" in low and ("http" in low or "url" in low):
                print(f"  ССЫЛКА в {t['path']}: {line.strip()[:120]}")
                break


def check_choco() -> None:
    print("\n=== chocolatey: пакет vb-cable ===")
    try:
        url = ("https://community.chocolatey.org/api/v2/package/vb-cable/43.0.0")
        data = get(url, timeout=40)
        print(f"  nupkg скачан: {len(data) / 1024:.0f} КБ")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            print(f"  файлов в пакете: {len(names)}")
            for n in names:
                print(f"    {n}")
            for n in names:
                if n.lower().endswith((".ps1", ".txt")):
                    try:
                        txt = z.read(n).decode("utf-8", "replace")
                    except Exception:
                        continue
                    for line in txt.splitlines():
                        if "http" in line and ("zip" in line.lower() or "exe" in line.lower()):
                            print(f"  URL в {n}: {line.strip()[:130]}")
    except Exception as exc:
        print(f"  ошибка: {exc}")


def main() -> None:
    for r in REPOS:
        check_repo(r)
    check_choco()


if __name__ == "__main__":
    main()
