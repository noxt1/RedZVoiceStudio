"""Загрузчик одной модели в кэш HuggingFace (отдельный процесс).

Запускается движком как дочерний процесс, чтобы загрузку можно было
отменить (terminate) и чтобы тяжёлый сетевой код не блокировал IPC.
HuggingFace сам проверяет контрольные суммы файлов (LFS sha256) и
докачивает недокачанное при следующем запуске.

    python download_model.py --repo Helsinki-NLP/opus-mt-en-ru
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--revision", default="main")
    args = ap.parse_args()
    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:  # noqa: BLE001
        print(f"нет huggingface_hub: {exc}", file=sys.stderr)
        return 2
    try:
        path = snapshot_download(args.repo, revision=args.revision,
                                 max_workers=4)
    except Exception as exc:  # noqa: BLE001
        print(f"ошибка загрузки {args.repo}: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
