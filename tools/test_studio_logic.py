"""Тест логики приложения без GUI: загрузка фраз, перевод, payload.

    python tools\\test_studio_logic.py
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_core as core  # noqa: E402
import studio_paths as sp  # noqa: E402
import translate  # noqa: E402


def main() -> None:
    sp.seed_workspace()

    # 1. Пресет из lines.json: испанский + русский перевод
    preset = []
    for line in core.load_lines():
        preset.append({"id": line["id"], "text": line["es"], "ru": line.get("ru", "")})
    print(f"1. пресет: {len(preset)} фраз, без перевода: "
          f"{[p['id'] for p in preset if not p['ru']] or 'нет'}")

    # 2. Перевод своей фразы RU -> ES
    es, ok = translate.translate_ru_to_es("Не двигайся, руки вверх!")
    print(f"2. перевод: 'Не двигайся, руки вверх!' -> '{es}' (ok={ok})")

    # 3. Payload для озвучки (идёт в файл, не в argv)
    payload = [{"id": p["id"], "text": p["text"], "ru": p["ru"]} for p in preset]
    payload.append({"id": "32", "text": es, "ru": "Не двигайся, руки вверх!"})
    path = os.path.join(sp.workspace(), "phrases_payload.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    print(f"3. payload: {len(payload)} фраз -> {os.path.basename(path)} "
          f"({os.path.getsize(path)} байт)")

    # 4. Проверка, что файл читается движком без потерь кириллицы
    with open(path, encoding="utf-8") as fh:
        back = json.load(fh)
    ok_ru = sum(1 for p in back if p.get("ru"))
    print(f"4. чтение файла: {len(back)} фраз, с русским: {ok_ru}")
    assert len(back) == len(payload), "потеря фраз при записи/чтении"
    assert ok_ru == len(payload), "потеря кириллицы"
    print("   OK — потерь нет")


if __name__ == "__main__":
    main()
