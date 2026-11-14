"""Проверка загрузки фраз и сборки payload для озвучки.

    python tools\\test_phrase_flow.py
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_core as core  # noqa: E402


def main() -> None:
    preset = []
    for line in core.load_lines():
        preset.append({"id": line["id"], "text": line["es"], "ru": line.get("ru", "")})

    print(f"пресет загружен: {len(preset)}")
    no_ru = [p["id"] for p in preset if not p["ru"]]
    print("без русского перевода:", no_ru if no_ru else "нет — у всех есть")
    for p in preset[:3] + preset[10:12]:
        print(f"  {p['id']}  {p['text'][:30]:<32} -> {p['ru']}")

    payload = [{"id": p["id"], "text": p["text"], "ru": p["ru"]} for p in preset]
    payload.append({"id": "32", "text": "No te muevas!", "ru": "Не двигайся!"})
    print(f"payload для озвучки: {len(payload)}")

    out = os.path.join(ROOT, "tools", "payload_test.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    print("payload сохранён ->", out)


if __name__ == "__main__":
    main()
