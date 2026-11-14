"""Где взять полный установщик виртуального кабеля.

vb-audio.com недоступен с этой машины, поэтому проверяем:
  * пакеты chocolatey — установщик может быть вложен в nupkg;
  * GitHub-репозитории — ищем файлы-установщики (>500 КБ, .zip/.exe).

    python tools\\find_cable_installer.py
"""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request
import zipfile

UA = {"User-Agent": "RedZVoiceStudio/1.0"}
CHOCO_PKGS = ["voicemeeter", "voicemeeter-potato", "voicemeeter-banana", "vb-cable"]
REPO_TERMS = ["VB-CABLE installer", "VBCABLE_Driver_Pack45", "virtual audio cable windows",
               "VB-CABLE driver install", "Voicemeeter8Setup"]


def get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def api(url: str, timeout: int = 25):
    return json.loads(get(url, timeout).decode("utf-8", "replace"))


def check_choco() -> None:
    print("=== chocolatey: вложенные установщики ===")
    for pkg in CHOCO_PKGS:
        try:
            raw = get(f"https://community.chocolatey.org/api/v2/package/{pkg}")
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception as exc:
            print(f"  {pkg}: {exc}")
            continue
        versions = [v["Version"] for v in data.get("Versions", [])]
        if not versions:
            print(f"  {pkg}: нет версий")
            continue
        ver = versions[0]
        try:
            blob = get(f"https://community.chocolatey.org/api/v2/package/{pkg}/{ver}")
        except Exception as exc:
            print(f"  {pkg} {ver}: nupkg не скачался ({exc})")
            continue
        print(f"  {pkg} {ver}: nupkg {len(blob) / 1024:.0f} КБ")
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
        except Exception as exc:
            print(f"    не zip: {exc}")
            continue
        for n in z.namelist():
            if n.lower().endswith((".zip", ".exe", ".msi", ".7z")):
                print(f"    ВЛОЖЕНО: {n}  ({z.getinfo(n).file_size / 1024:.0f} КБ)")
        for n in z.namelist():
            if n.lower().endswith(".ps1"):
                try:
                    txt = z.read(n).decode("utf-8", "replace")
                except Exception:
                    continue
                for line in txt.splitlines():
                    if "url" in line.lower() and "http" in line.lower():
                        print(f"    URL: {line.strip()[:120]}")


def check_github() -> None:
    print("\n=== GitHub: репозитории с установщиками ===")
    seen = set()
    for term in REPO_TERMS:
        q = urllib.parse.quote_plus(term)
        try:
            data = api(f"https://api.github.com/search/repositories?q={q}&per_page=6")
        except Exception as exc:
            print(f"  {term}: {exc}")
            continue
        for item in data.get("items", []):
            full = item["full_name"]
            if full in seen:
                continue
            seen.add(full)
            try:
                tree = api(f"https://api.github.com/repos/{full}/git/trees/HEAD?recursive=1")
            except Exception:
                continue
            big = [t for t in tree.get("tree", [])
                   if t.get("type") == "blob" and t.get("size", 0) > 400000
                   and t["path"].lower().endswith((".zip", ".exe", ".msi", ".7z"))]
            if big:
                print(f"  {full}:")
                for t in big:
                    print(f"     {t['size'] / 1024 / 1024:.1f} МБ  {t['path']}")


if __name__ == "__main__":
    check_choco()
    check_github()
