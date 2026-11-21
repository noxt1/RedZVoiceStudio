"""Глоссарий терминов и имён для перевода (ROADMAP 4.6–4.7).

Зачем: opus-mt уверенно ломает имена персонажей и топонимы («Arthur Morgan»
превращается в «Артура Моргана» не там, где надо, или в бессмыслицу), а
игровой сленг переводится буквально. Глоссарий закрывает это без дообучения
модели.

Механизм — «защита метками»:
  1. перед переводом совпавший термин заменяется на служебную метку
     `⟦G0⟧`, которую модель не пытается переводить;
  2. после перевода метка заменяется заранее заданным термином для целевого
     языка;
  3. если для языка перевода термина нет — возвращается исходная форма,
     то есть имя остаётся именем.

Файл `glossary.json` (рядом с движком, либо путь из `AURALOOM_GLOSSARY`):

    {"entries": [
        {"src": "Arthur Morgan", "ru": "Артур Морган", "en": "Arthur Morgan"},
        {"src": "sheriff", "ru": "шериф", "es": "sheriff"}
    ]}

`src` — как термин встречается в исходном тексте (без учёта регистра).
"""

from __future__ import annotations

import json
import os
import re

# Метка-заменитель. Проверено на opus-mt-en-ru: юникодные скобки вида ⟦G0⟧
# модель переписывает в «ЕЦГ0З», а латинская метка с цифрами переживает
# перевод во всех проверенных направлениях.
MARK = "ZQX{}QZ"
_MARK_RE = re.compile(r"Z\s*Q\s*X\s*(\d+)\s*Q\s*Z", re.IGNORECASE)

DEFAULT_ENTRIES: list[dict] = [
    {"src": "Arthur Morgan", "ru": "Артур Морган", "en": "Arthur Morgan",
     "es": "Arthur Morgan", "it": "Arthur Morgan"},
    {"src": "Dutch van der Linde", "ru": "Дач ван дер Линде",
     "en": "Dutch van der Linde", "es": "Dutch van der Linde"},
    {"src": "Blackwater", "ru": "Блэкуотер", "en": "Blackwater",
     "es": "Blackwater"},
    {"src": "Saint Denis", "ru": "Сен-Дени", "en": "Saint Denis",
     "es": "Saint Denis"},
    {"src": "Valentine", "ru": "Валентайн", "en": "Valentine",
     "es": "Valentine"},
    {"src": "sheriff", "ru": "шериф", "en": "sheriff", "es": "sheriff"},
    {"src": "bounty", "ru": "награда за голову", "en": "bounty",
     "es": "recompensa"},
    {"src": "posse", "ru": "банда", "en": "posse", "es": "banda"},
    # Частая ошибка ASR испанского: burro/asno слышится как show.
    {"src": "burro", "ru": "осёл", "en": "donkey", "es": "burro",
     "it": "asino"},
    {"src": "asno", "ru": "осёл", "en": "donkey", "es": "asno",
     "it": "asino"},
    # Имя, которое Whisper в испанской речи слышит как два слова («Mars al»).
    # Нужно прежде всего как подсказка hotwords в распознавании: без неё
    # переводчик получает «Марса» вместо «Маршала».
    {"src": "Marshall", "ru": "Маршал", "en": "Marshall",
     "es": "Marshall", "it": "Marshall"},
]


def default_path() -> str:
    """Где искать файл глоссария."""
    env = os.environ.get("AURALOOM_GLOSSARY", "").strip()
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    # движок запускается из рабочей папки (workspace\tools) — сначала рядом
    for cand in (os.path.join(os.path.dirname(here), "glossary.json"),
                 os.path.join(here, "glossary.json")):
        if os.path.exists(cand):
            return cand
    return os.path.join(os.path.dirname(here), "glossary.json")


def ensure_file(path: str | None = None) -> str:
    """Создать файл с терминами по умолчанию, если его ещё нет."""
    target = path or default_path()
    if os.path.exists(target):
        return target
    try:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump({"entries": DEFAULT_ENTRIES}, fh,
                      ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass
    return target


class Glossary:
    """Термины и замена их метками вокруг перевода."""

    def __init__(self, entries: list[dict] | None = None) -> None:
        self.entries: list[dict] = []
        self._patterns: list[tuple[re.Pattern, dict]] = []
        self.set_entries(DEFAULT_ENTRIES if entries is None else entries)

    def set_entries(self, entries: list[dict]) -> None:
        clean: list[dict] = []
        for e in entries or []:
            if not isinstance(e, dict):
                continue
            src = str(e.get("src", "")).strip()
            if not src:
                continue
            item = {"src": src}
            for k, v in e.items():
                if k != "src" and isinstance(v, str) and v.strip():
                    item[k] = v.strip()
            clean.append(item)
        # длинные термины первыми: «Arthur Morgan» должен победить «Arthur»
        clean.sort(key=lambda x: len(x["src"]), reverse=True)
        self.entries = clean
        self._patterns = [
            (re.compile(re.escape(e["src"]), re.IGNORECASE), e) for e in clean
        ]

    @classmethod
    def load(cls, path: str | None = None) -> "Glossary":
        target = path or default_path()
        try:
            with open(target, encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("entries", []) if isinstance(data, dict) else data
            if entries:
                return cls(entries)
        except Exception:  # noqa: BLE001
            pass
        return cls()

    def protect(self, text: str) -> tuple[str, list[dict]]:
        """Заменить термины метками. Возвращает (текст, список меток)."""
        if not text or not self._patterns:
            return text, []
        used: list[dict] = []
        out = text
        for pattern, entry in self._patterns:
            def repl(_m, entry=entry):
                used.append(entry)
                return MARK.format(len(used) - 1)
            out = pattern.sub(repl, out)
        return out, used

    def restore(self, text: str, used: list[dict], dst: str) -> str:
        """Вернуть термины на место в форме целевого языка."""
        if not text or not used:
            return text
        def sub(m):
            i = int(m.group(1))
            term = ""
            if 0 <= i < len(used):
                term = used[i].get(dst) or used[i].get("src", "")
            # термин в начале фразы пишется с большой буквы
            if term and m.start() == 0:
                term = term[0].upper() + term[1:]
            return term

        # модель может разбить метку пробелами или сменить регистр —
        # поэтому ищем регулярным выражением, а не точной подстрокой
        out = _MARK_RE.sub(sub, text)
        # нерасшифрованные остатки (номер вне диапазона) просто убираем
        return _MARK_RE.sub("", out).strip() if _MARK_RE.search(out) else out.strip()


def translate(text: str, dst: str, mt) -> str:
    """Перевести с защитой терминов. `mt` — функция перевода одного текста."""
    g = translate.glossary or Glossary()
    protected, used = g.protect(text)
    out = mt(protected)
    return g.restore(out, used, dst)


# Глоссарий по умолчанию для функции translate(); движок подставляет свой.
translate.glossary = None  # type: ignore[attr-defined]
