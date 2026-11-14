r"""Проверка реплик на соответствие ограничениям проекта RedZ.

П.3.2 правил RedZ: «Запрещено косвенное упоминание или оскорбление родственников
в любых чатах в том числе в любых средствах связи или оповещения».

Скрипт ищет в текстах реплик слова, связанные с родителями/родственниками,
и отдельно проверяет, что мат есть, а родственников — нет.

Проверяются ВСЕ языки реплики (es, en, ow, it) — ограничения касаются
любого текста, который уходит в игру. Для английского и итальянского
списки свои: иначе испанские слова ловят куски чужих слов
(«tio» в «tarnation», «prima» в итальянском «Spara prima!»).

    python tools\check_rules.py
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Слова, которые нельзя использовать: прямые или косвенные упоминания семьи.
FAMILY_WORDS_ES = [
    "madre", "mama", "mamá", "papá", "papa", "padre", "padres",
    "hermano", "hermana", "hijo", "hija", "abuelo", "abuela", "tia", "tía",
    "tio", "tío", "sobrino", "primo", "prima", "esposa", "esposo", "novia",
    "novio", "concha", "conchita", "pendeja", "pendejo de tu",
    "tu madre", "tu mama", "tu papa", "tu padre", "mi madre", "mi mama",
    "mi papa", "mi padre", "madre del", "concha de", "hijode", "hijo de",
    "hija de", "madre mia", "puta madre", "maldita madre", "chinga madre",
    "chinga a tu madre", "tu madre", "tu concha", "mi concha",
]

FAMILY_WORDS_EN = [
    "mother", "mom", "mommy", "mum", "father", "dad", "daddy", "sister",
    "brother", "son", "daughter", "grandmother", "grandma", "grandfather",
    "grandpa", "aunt", "uncle", "cousin", "wife", "husband", "your mother",
    "your father", "his mother", "her mother", "their mother",
]

FAMILY_WORDS_IT = [
    "madre", "mamma", "padre", "papà", "sorella", "fratello", "figlio",
    "figlia", "nonna", "nonno", "zia", "zio", "cugino", "moglie", "marito",
]

# Списки слов по полям реплики.
FAMILY_BY_FIELD = {
    "es": FAMILY_WORDS_ES,
    "en": FAMILY_WORDS_EN,
    "ow": FAMILY_WORDS_EN,      # олдвест — это английский
    "it": FAMILY_WORDS_IT,
}

# Признаки мата: должен присутствовать, чтобы набор не скатился в «вежливый».
SWEAR_MARKERS = [
    "pinche", "cabron", "cagón", "chinga", "chingada", "pendejo", "culero",
    "joder", "carajos", "no manches", "no mames", "chingada", "a huevo",
    "neta", "qué pedo", "que pedo", "me chinga", "no te la ",
]


def find_family_words(text: str, words: list[str]) -> list[str]:
    """Найти слова о родственниках (по границам слов, а не подстроке)."""
    low = (text or "").lower()
    hits = []
    for word in words:
        pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(pattern, low):
            hits.append(word)
    return hits


def main() -> None:
    lines_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "lines.json")
    with open(lines_file, encoding="utf-8") as fh:
        data = json.load(fh)

    violations = []
    for line in data["lines"]:
        for field, words in FAMILY_BY_FIELD.items():
            text = str(line.get(field, "") or "")
            if not text:
                continue
            for word in find_family_words(text, words):
                violations.append((line["id"], field, text, word))

    print(f"Проверено реплик: {len(data['lines'])}")

    if violations:
        print("\n!! НАРУШЕНИЯ (упоминание родственников):")
        for lid, field, text, word in violations:
            print(f"  [{lid}][{field}] {text!r}  -> найдено: {word!r}")
        raise SystemExit(1)

    print("Родственники не упоминаются — п.3.2 соблюдён.")

    # Отдельно: считаем, сколько реплик несут мат
    with_mat = [l for l in data["lines"]
                if any(m in l["es"].lower() for m in SWEAR_MARKERS)]
    print(f"\nРеприк с матом: {len(with_mat)} из {len(data['lines'])}")
    print("Категории:", ", ".join(sorted({l["cat"] for l in data["lines"]})))

    # Проверка уникальности id и клавиш
    ids = [l["id"] for l in data["lines"]]
    keys = [l["key"] for l in data["lines"]]
    if len(set(ids)) != len(ids):
        print("\n!! Дублирующиеся id")
        raise SystemExit(1)
    if len(set(keys)) != len(keys):
        dupes = {k for k in keys if keys.count(k) > 1}
        print(f"\n!! Дублирующиеся клавиши: {dupes}")
        raise SystemExit(1)
    print(f"id и клавиши уникальны: {len(ids)} реплик, {len(set(keys))} клавиш.")

    # Порядок id должны идти подряд
    expected = [f"{i:02d}" for i in range(1, len(ids) + 1)]
    if ids != expected:
        print(f"\n!! id не подряд: {ids}")
        raise SystemExit(1)
    print("Порядок id корректный.")

    # Все языки должны быть переведены
    missing = []
    for line in data["lines"]:
        for field in FAMILY_BY_FIELD:
            if not str(line.get(field, "") or "").strip():
                missing.append(f"{line['id']}:{field}")
    if missing:
        print(f"\n!! Нет перевода: {', '.join(missing)}")
        raise SystemExit(1)
    print("Переведены все языки: es, en, ow, it.")


if __name__ == "__main__":
    main()
