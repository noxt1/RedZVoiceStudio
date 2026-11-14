"""Western Style Engine — стилизация английского в стиле Дикого Запада.

Old West — это не отдельный язык, а стиль английской речи.
Конвейер: RU → обычный EN (opus-mt-ru-en) → Western Style Engine → XTTS (en).

Три профиля стилизации:
  * Light   — лёгкие характерные выражения, massima естественность
  * Classic — узнаваемая речь Дикого Запада (по умолчанию)
  * Strong  — более выраженная кинематографическая стилизация

Правила:
  * Не добавлять partner/pardner автоматически в конец предложений.
  * Не использовать каждое выражение в каждой фразе.
  * Сохранять имена, числа, игровые ники, термины, отрицания, вопросы.
  * Не стилизовать другие языки (es, it и т.п.).
"""

from __future__ import annotations

import re
from enum import Enum


class WesternStyle(Enum):
    LIGHT = "light"
    CLASSIC = "classic"
    STRONG = "strong"


# --------------------------------------------------------------------------
# Точные замены фраз (ключ — английский без знаков препинания, нижний регистр)
# Значение: dict[style, замена] или просто строка (применимо ко всем стилям)
# --------------------------------------------------------------------------

_PHRASE_DICT: dict[str, dict[WesternStyle, str] | str] = {
    # Приветствия
    "hello": {
        WesternStyle.LIGHT: "Hello!",
        WesternStyle.CLASSIC: "Howdy!",
        WesternStyle.STRONG: "Howdy there!",
    },
    "hi": {
        WesternStyle.LIGHT: "Hi!",
        WesternStyle.CLASSIC: "Howdy!",
        WesternStyle.STRONG: "Howdy, stranger!",
    },
    "good morning": {
        WesternStyle.LIGHT: "Good morning!",
        WesternStyle.CLASSIC: "Mornin'!",
        WesternStyle.STRONG: "Top of the mornin' to ya!",
    },
    "goodbye": {
        WesternStyle.LIGHT: "Goodbye!",
        WesternStyle.CLASSIC: "So long!",
        WesternStyle.STRONG: "So long, partner!",
    },
    # Благодарность
    "thank you": {
        WesternStyle.LIGHT: "Thank you.",
        WesternStyle.CLASSIC: "Much obliged.",
        WesternStyle.STRONG: "I'm much obliged to ya.",
    },
    "thanks for your help": {
        WesternStyle.LIGHT: "Thanks for your help.",
        WesternStyle.CLASSIC: "Much obliged for your help.",
        WesternStyle.STRONG: "I'm much obliged for your help, pardner.",
    },
    # Предложение помощи
    "i'll help you": {
        WesternStyle.LIGHT: "I'll help you.",
        WesternStyle.CLASSIC: "I'll lend you a hand.",
        WesternStyle.STRONG: "I'll lend you a hand there, friend.",
    },
    # Прощание / уход
    "let's leave": {
        WesternStyle.LIGHT: "Let's leave.",
        WesternStyle.CLASSIC: "Let's mosey.",
        WesternStyle.STRONG: "Let's mosey on outta here.",
    },
    "i surrender": {
        WesternStyle.LIGHT: "I surrender!",
        WesternStyle.CLASSIC: "I surrender!",
        WesternStyle.STRONG: "I surrender, don't shoot!",
    },
    # Угрозы / команды (не меняем смысл)
    "enemy on the left": "Enemy on the left!",
    "enemy on the right": "Enemy on the right!",
    "don't shoot": "Don't shoot!",
    "stop": "Hold it right there!",
    "drop your weapon": "Drop your shooting iron!",
    "hands up": "Hands up!",
    # Отрицания и вопросы (не трогаем смысл)
    "i don't know": {
        WesternStyle.LIGHT: "I don't know.",
        WesternStyle.CLASSIC: "I reckon I don't know.",
        WesternStyle.STRONG: "I reckon I ain't got a clue.",
    },
    "i don't know.": {
        WesternStyle.LIGHT: "I don't know.",
        WesternStyle.CLASSIC: "I reckon I don't know.",
        WesternStyle.STRONG: "I reckon I ain't got a clue.",
    },
    # Подтверждение
    "yes": {
        WesternStyle.LIGHT: "Yes.",
        WesternStyle.CLASSIC: "Yep.",
        WesternStyle.STRONG: "Yep, that's right.",
    },
    "no": {
        WesternStyle.LIGHT: "No.",
        WesternStyle.CLASSIC: "Nope.",
        WesternStyle.STRONG: "Nope, not a chance.",
    },
}

# --------------------------------------------------------------------------
# Замены отдельных слов (контекстно-безопасные, смысл не меняется)
# --------------------------------------------------------------------------

_WORD_DICT: dict[str, dict[WesternStyle, str] | str] = {
    "friend": {
        WesternStyle.LIGHT: "friend",
        WesternStyle.CLASSIC: "pal",
        WesternStyle.STRONG: "pardner",
    },
    "hello": "howdy",
    "hey": "howdy",
    "goodbye": "so long",
    "police": "lawmen",
    "gun": "shooting iron",
    "bullet": "slug",
    "jail": "hoosegow",
    "money": "cash",
    "horse": "mount",
    "ride": "mosey",
    "go": "mosey",
    "move": "git",
    "yes": "yep",
    "no": "nope",
    "kid": "young'un",
    "child": "young'un",
}

# --------------------------------------------------------------------------
# Слова-маркеры уже ковбойского стиля (не добавляем partner если они есть)
# --------------------------------------------------------------------------

_STYLE_MARKERS = (
    "partner", "pardner", "kid", "mister", "pal", "reckon", "y'all",
    "ain't", "gonna", "buddy", "shooting iron", "lawmen", "howdy",
    "much obliged", "mosey", "hoosegow", "pard",
)

# --------------------------------------------------------------------------
# Защита: имена, числа, ники, игровые термины не трогаем
# --------------------------------------------------------------------------

# Простая защита: слова, написанные с большой буквы внутри предложения (не в начале)
# и всецифровые токены считаются потенциальными именами/терминами
_PROTECTED_PATTERN = re.compile(r"\b[A-Z][a-z]+\b|\b\d+\b")


def _protect_terms(text: str) -> list[tuple[str, str]]:
    """Найти потенциальные имена/термины для защиты."""
    return [(m.group(), m.group()) for m in _PROTECTED_PATTERN.finditer(text)]


def _apply_word_replacements(
    text: str, style: WesternStyle
) -> str:
    """Применить замены слов с учётом стиля."""
    result = text
    for src, dst in _WORD_DICT.items():
        if isinstance(dst, dict):
            replacement = dst.get(style, dst.get(WesternStyle.CLASSIC, src))
        else:
            replacement = dst
        if replacement != src:
            result = re.sub(
                rf"\b{re.escape(src)}\b",
                replacement,
                result,
                flags=re.IGNORECASE,
            )
    return result


def _should_add_style_marker(text: str) -> bool:
    """Проверить, есть ли уже ковбойский маркер в тексте."""
    low = text.lower()
    return any(marker in low for marker in _STYLE_MARKERS)


def _format_phrase(text: str, style: WesternStyle) -> str:
    """Применить точную замену фразы из словаря."""
    key = text.lower().rstrip(" .!?")
    if key in _PHRASE_DICT:
        entry = _PHRASE_DICT[key]
        if isinstance(entry, dict):
            return entry.get(style, entry.get(WesternStyle.CLASSIC, text))
        return entry
    return text


class WesternStyleEngine:
    """Движок стилизации английского в стиле Дикого Запада.

    Поддерживает три профиля: Light, Classic, Strong.
    Не добавляет partner автоматически в конец предложений.
    """

    def __init__(self, style: WesternStyle = WesternStyle.CLASSIC) -> None:
        self.style = style

    def set_style(self, style: WesternStyle) -> None:
        self.style = style

    def style_text(self, text: str) -> str:
        """Стилизовать английский текст в стиле Дикого Запада.

        Порядок:
          1. Точная замена фразы из словаря (если есть)
          2. Замена отдельных слов
          3. Стилевые штрихи в зависимости от профиля
        """
        if not text or not text.strip():
            return text

        # 1. Точная замена фразы
        result = _format_phrase(text, self.style)

        # 2. Замена слов (если фраза не найдена в точном словаре)
        if result == text:
            result = _apply_word_replacements(text, self.style)

        # 3. Дополнительные стилевые штрихи (только Classic/Strong)
        if self.style != WesternStyle.LIGHT:
            result = self._apply_style_flourishes(result)

        return result

    def _apply_style_flourishes(self, text: str) -> str:
        """Добавить характерные обороты без потери смысла."""
        low = text.lower()

        # Если уже есть ковбойский маркер, не перегружаем
        if _should_add_style_marker(text):
            return text

        # Very light flourishes — только если текст короткий и не содержит маркеров
        words = text.split()
        if len(words) <= 10:
            # klassic: добавить reckon в начале предложения с "I think"
            if self.style == WesternStyle.CLASSIC:
                if text.lower().startswith("i think "):
                    text = "I reckon " + text[len("i think "):]
                    return text
            # strong: чуть больше вольностей, но без partner
            if self.style == WesternStyle.STRONG:
                if text.lower().startswith("i don't know"):
                    return "I reckon I don't know."
                if text.lower().startswith("yes, "):
                    return "Yep, " + text[len("yes, "):]

        return text

    def style_batch(self, texts: list[str]) -> list[str]:
        """Стилизовать несколько фраз."""
        return [self.style_text(t) for t in texts]


def style_to_western(
    text: str, style: WesternStyle = WesternStyle.CLASSIC
) -> str:
    """Функция-утилита для быстрой стилизации одной фразы."""
    engine = WesternStyleEngine(style)
    return engine.style_text(text)


# Сохраняем обратную совместимость: старое имя to_oldwest
def to_oldwest(text: str) -> str:
    """Стилизовать английский в стиле вестерна (классический профиль).

    Обратная совместимость со старым API.
    """
    return style_to_western(text, WesternStyle.CLASSIC)
