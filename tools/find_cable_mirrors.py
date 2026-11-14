"""Поиск зеркал установщиков виртуального аудиокабеля.

Сайт vb-audio.com с этой машины недоступен (таймаут), поэтому ищем
зеркала на доступных хостах (GitHub, HuggingFace).

    python tools\\find_cable_mirrors.py
"""

from __future__ import annotations

import json
import os
import urllib.request

UA = {"User-Agent": "RedZVoiceStudio/1.0"}


def get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main() -> None:
    print("=== GitHub: репозитории с зеркалами ===")
    seen = set()
    for term in ("VBCABLE", "Voicemeeter", "vb-cable", "virtual-audio-cable"):
        try:
            data = json.loads(get(f"https://api.github.com/search/repositories"
                                 f"?q={term}&per_page=10"))
        except Exception as exc:
            print(f"  {term}: ошибка {exc}")
            continue
        print(f"  --- {term}: всего {data.get('total_count')} ---")
        for item in data.get("items", []):
            full = item["full_name"]
            if full in seen:
                continue
            seen.add(full)
            desc = (item.get("description") or "")[:68]
            size = item.get("size", 0)
            print(f"    {full:<45} size={size:<8} {desc}")

    print("\n=== проверка доступности хостов ===")
    for url in ("https://www.vb-audio.com/Cable/",
                "https://download.vb-audio.com/Download_CABLE/Voicemeeter8Setup_v3122.zip",
                "https://github.com",
                "https://huggingface.co",
                "https://objects.githubusercontent.com",
                "https://community.chocolatey.org/api/v2/package/vb-cable"):
        try:
            req = urllib.request.Request(url, headers=UA, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as resp:
                print(f"  OK   {url}  ({resp.status})")
        except Exception as exc:
            msg = str(exc)
            print(f"  FAIL {url}  -> {msg[:70]}")


if __name__ == "__main__":
    main()
