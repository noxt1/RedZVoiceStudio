"""Скачать XTTS-v2 в кэш HuggingFace движка (пофайлово).

snapshot_download не тянет LFS-большие файлы. Качаем каждый файл
явно через hf_hub_download — так LFS-указатели заменяются данными.

Запуск движком:
    %LOCALAPPDATA%\\Auraloom\\engine\\Scripts\\python.exe tools/fetch_xtts.py
"""

from __future__ import annotations

import os
import sys

REPO = "tts-hub/XTTS-v2"
FILES = [
    "config.json",
    "vocab.json",
    "hash.md5",
    "model.pth",             # ~1.8 ГБ
    "dvae.pth",              # ~360 МБ
    "mel_stats.pth",
    "speakers_xtts.pth",
]


def main() -> int:
    try:
        from huggingface_hub import hf_hub_download
    except Exception as exc:
        print(f"нет huggingface_hub: {exc}")
        return 1

    target = os.path.expanduser(r"~\.cache\huggingface\hub")
    print(f"кэш: {target}")
    print(f"модель: {REPO}")

    ok = 0
    fail = 0
    for fn in FILES:
        print(f"  качаю {fn} …", flush=True)
        try:
            p = hf_hub_download(repo_id=REPO, filename=fn, cache_dir=target)
            size = os.path.getsize(p) if os.path.exists(p) else 0
            # LFS-указатель обычно < 200 байт
            if size < 200 and fn.endswith(".pth"):
                print(f"    ПЛОХО: {size} байт (LFS-указатель)")
                fail += 1
            else:
                print(f"    ок: {size / 1024 / 1024:.1f} МБ")
                ok += 1
        except Exception as exc:
            print(f"    ошибка: {exc}")
            fail += 1

    print(f"\nитого: ок={ok}, ошибок={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())