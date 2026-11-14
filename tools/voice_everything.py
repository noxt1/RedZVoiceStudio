"""Озвучить все фразы панели голосом пользователя (то же, что кнопка в приложении).

    python tools\\voice_everything.py

Берёт образец голоса из рабочей папки, собирает список фраз (пресет из
lines.json + свои фразы из phrases.json) и запускает клонирование.
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import studio_core as core  # noqa: E402
import studio_paths as sp  # noqa: E402


def build_payload() -> list[dict]:
    payload = [{"id": l["id"], "text": l["es"], "ru": l.get("ru", "")}
               for l in core.load_lines()]
    custom_path = os.path.join(sp.workspace(), "phrases.json")
    if os.path.exists(custom_path):
        try:
            with open(custom_path, encoding="utf-8") as fh:
                saved = json.load(fh)["phrases"]
            known = {p["id"] for p in payload}
            for item in saved:
                if item.get("id") not in known and item.get("text"):
                    payload.append({"id": item["id"], "text": item["text"],
                                    "ru": item.get("ru", "")})
        except Exception as exc:  # noqa: BLE001
            print("Не прочитал phrases.json:", exc)
    return payload


def main() -> None:
    sp.seed_workspace()
    reference = sp.output_paths()["reference"]
    if not os.path.exists(reference):
        sys.exit("Нет образца голоса (reference.wav) — запиши подсказки на вкладке «Голос».")

    payload = build_payload()
    path = os.path.join(sp.workspace(), "phrases_payload.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)

    print(f"Образец: {reference}")
    print(f"Фраз к озвучке: {len(payload)}")
    print("Запускаю клонирование...\n")

    code = core.clone_all(reference, attempts=6, texts=payload,
                          on_line=lambda line: print(line, flush=True))
    print(f"\nКод возврата: {code}")
    if code == 0:
        moved = core.distribute()
        print(f"Разложено: {moved['ogg']} ogg -> sounds/, {moved['mp3']} mp3 -> player/mp3/")


if __name__ == "__main__":
    main()
