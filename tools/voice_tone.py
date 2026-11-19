"""«Живость» речи: голос должен звучать злее или добрее по смыслу фразы.

XTTS-v2 умеет менять подачу: temperature/top_p/top_k (разброс) и speed
(темп). Но для одинаковых параметров ругательство и вежливая фраза звучат
одинаково — а игроку в RedZ нужна разная подача:

  * «Хрень твою, ты чё творишь?»  -> злее, резче, быстрее
  * «Привет, рад тебя видеть»    -> теплее, мягче, спокойнее

Поэтому по тексту определяем ТОН и подбираем параметры синтеза.

Используется и движком живого перевода (tools/live_translate.py), и
озвучкой фраз (app/voice_studio.py) — одна логика на оба случая.

    python tools\\voice_tone.py "Хрень твою"
"""

from __future__ import annotations

import re

# --- словари тона (испанский + русский) ---

AGGRESSIVE_WORDS = (
    # испанский: ругательства и резкие слова (основы — ловим словоформы:
    # maldito/malditos, cabron/cabrones)
    "maldit", "puta", "puto", "mierd", "joder", "jodete", "jodid",
    "cabron", "hijoputa", "hijo", "imbecil", "gilipollas", "pendej",
    "maricon", "marica", "culer", "ching", "verga", "cono", "concha",
    "polvo", "estupid", "idiot", "basura", "asqueros", "odiar", "odia",
    "matar", "pelotud", "malparid", "mamon", "carajo", "hostia", "gilipollez",
    "zorra", "perra", "callado", "callate", "tonto", "idiota", "imbécil",
    # русский (основы — ловим и словоформы: ублюдок/ублюдки, сраный/сраные)
    "хуй", "хуя", "хуе", "хуес", "хуев", "хуи", "хуё", "хуей",
    "пизд", "пизда", "пизду", "пизде", "пиздой", "ебан", "ебат", "ебать",
    "блядь", "бляд", "бля", "сука", "суки", "мудак", "мудила", "гандон",
    "долбоеб", "долбоёб", "ебану", "ебаный", "ебаная", "заебись",
    "чмо", "чмошник", "ублюдок", "сволочь", "сволочи",
    "тварь", "убить", "убью", "уеб", "уёб", "задолба", "достал", "заеб",
    "выеб", "выебан", "пидор", "пидорка", "хрень", "хрени", "хрен",
    "долби", "долблю", "залупа", "залуп", "ссан", "ссать", "сраный",
    "сраные", "сраная", "сраное", "яица", "шлюха", "ублюд", "срати",
    "срать", "мразь", "мраз", "сран", "сволоч", "долбо",
)

FRIENDLY_WORDS = (
    # испанский
    "hola", "buenos dias", "buenas tardes", "buenas noches", "gracias",
    "por favor", "amigo", "amiga", "hermano", "hermana", "bienvenido",
    "encantado", "mucho gusto", "lo siento", "perdona", "disculpa",
    "feliz", "alegre", "alegria", "cariño", "carino", "abrazo", "sonrisa",
    "tranquilo", "tranquila", "paz", "suerte", "me gusta", "te quiero",
    "adios", "hasta luego", "hasta pronto", "nos vemos", "clavar",
    "vaamos", "vamos", "bromas", "broma", "chiste", "jaja", "jajaja",
    "lindo", "linda", "bueno", "claro", "vale", "ok", "bien", "gracias",
    # русский
    "привет", "здравствуй", "здравствуйте", "спасибо", "пожалуйста",
    "друг", "друзья", "брат", "братишка", "добро пожаловать", "рад",
    "извини", "извините", "прости", "счастлив", "радость", "улыб",
    "удачи", "спокойно", "люблю", "до свидания", "пока", "давай",
    "шутка", "прикол", "ха", "хаха", "хахаха", "круто", "класс",
)

# --- настройки XTTS по тону ---
#
# Замер (research/bench_liveliness.py): ВЫШЕ temperature=0.9 XTTS выдаёт
# кашу («Ahora mío, me amo chavusta verde, puzzle» — разборчивость 12%).
# При этом F0 σ даже ПАДАЕТ с ростом температуры (47 -> 33 Гц).
# Значит температура — не рычаг «живости», а рычаг шума.
#
# Настоящий рычаг — enable_text_splitting: XTTS тогда ведёт каждую фразу
# как отдельное высказывание со своей интонацией (размах высоты 213 Гц
# против 148). Поэтому он включён ВСЕГДА, а тон сдвигает параметры мягко.

# Спокойный/нейтральный: умеренный разброс, спокойный темп.
#
# Правки Этап C.7.8 (жалобы «неживо, монотонно»):
#  * temperature 0.75 -> 0.79: даёт интонационное разнообразие.
#    Выше 0.82 XTTS начинает «говорить кашей» — потолок жёсткий.
#  * top_k 50 -> 55, top_p 0.86 -> 0.88 — больше вариативности.
#  * speed 0.95: не тараторит, но и не вялый.
#  * repetition_penalty = 10.0 (дефолт XTTS): ниже 8 — зацикливание.
NEUTRAL = {"temperature": 0.79, "top_p": 0.88, "top_k": 55, "speed": 0.96,
           "repetition_penalty": 10.0}

# Злой/резкий: больше разброса и эмоции, но не быстрее (иначе тараторит).
AGGRESSIVE = {"temperature": 0.82, "top_p": 0.90, "top_k": 62, "speed": 0.99,
              "repetition_penalty": 10.0}

# Тёплый/дружелюбный: мягче, теплее.
FRIENDLY = {"temperature": 0.74, "top_p": 0.86, "top_k": 48, "speed": 0.94,
            "repetition_penalty": 10.0}

# Энергичный: живо, но в рамках разборчивости.
ENERGETIC = {"temperature": 0.80, "top_p": 0.89, "top_k": 58, "speed": 0.98,
             "repetition_penalty": 10.0}

TONE_NAMES = {
    "aggressive": "злой",
    "friendly": "добрый",
    "energetic": "энергичный",
    "neutral": "нейтральный",
}


def _normalize(text: str) -> str:
    """Нижний регистр без пунктуации и без акцентов — для поиска слов.

    Акценты снимаем: иначе «cabrón» не найдёт основу «cabron».
    """
    import unicodedata
    text = text.lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _count_hits(text: str, words: tuple[str, ...]) -> int:
    """Сколько слов из списка встречается в тексте.

    Сравниваем по ОСНОВЕ слова: «maldit» ловит «maldito» и «malditos»,
    «сран» — «сраный» и «сраные». Основы короче 4 букв пропускаем —
    они дают ложные срабатывания.
    """
    if not text:
        return 0
    tokens = text.split()
    hits = 0
    for stem in words:
        if len(stem) < 4:
            continue
        for tok in tokens:
            if tok == stem or tok.startswith(stem):
                hits += 1
                break
    return hits


def detect_tone(text: str) -> str:
    """Определить тон речи: aggressive / friendly / energetic / neutral."""
    if not text or not text.strip():
        return "neutral"
    norm = _normalize(text)

    aggressive = _count_hits(norm, AGGRESSIVE_WORDS)
    friendly = _count_hits(norm, FRIENDLY_WORDS)

    # Знаки восклицания — тоже признак энергии
    bangs = text.count("!") + text.count("¡")

    if aggressive >= 1:
        return "aggressive"
    if friendly >= 1:
        return "friendly"
    if bangs >= 2:
        return "energetic"
    return "neutral"


def detect_tone_pair(ru: str, es: str = "") -> str:
    """Тон по РУССКОМУ тексту, а если он нейтральный — по испанскому.

    Перевод часто СМЯГЧАЕТ эмоцию: «Вы ссаны ублюдки!» превращается в
    «¿Qué tal mi juego?» — и по испанскому тон уже не определить.
    """
    tone = detect_tone(ru)
    if tone == "neutral" and es:
        tone = detect_tone(es)
    return tone


def params_for_tone(tone: str) -> dict:
    """Параметры синтеза XTTS для тона."""
    return {
        "aggressive": dict(AGGRESSIVE),
        "friendly": dict(FRIENDLY),
        "energetic": dict(ENERGETIC),
        "neutral": dict(NEUTRAL),
    }.get(tone, dict(NEUTRAL))


def apply_punctuation(text: str, tone: str) -> str:
    """Расставить знаки препинания по тону.

    ЗАЧЕМ: перевод (opus-mt) почти никогда не ставит «!» — и XTTS читает
    фразу ровно, без эмоции. Знак препинания — самый дешёвый способ
    вернуть интонацию: слова те же, подача другая.

    Правка C.7.8 (жалобы «неживо»): добавлены паузы-многоточия и
    вопросительные знаки для нейтральных фраз, чтобы речь не была
    монотонной. XTTS реагирует на пунктуацию как на интонацию.
    """
    text = (text or "").strip()
    if not text:
        return text
    if tone in ("aggressive", "energetic"):
        # завершаем энергично
        if not text.endswith(("!", "?")):
            text = text.rstrip(".") + "!"
        return text
    if tone == "friendly":
        # мягкая улыбка: точка меняется на «!», но без «¡» (это крик)
        if text.endswith("."):
            text = text[:-1] + "!"
        return text
    # Нейтральный тон: НЕ вставляем запятую в середину фразы.
    # Раньше здесь ставилась запятая после половины слов любой фразы
    # длиной 4–18 слов: «Es ese tu burro» -> «Es ese, tu burro».
    # XTTS честно читает эту паузу, и речь звучит рвано и «не по-человечески».
    # Живость дают тон/скорость и естественная пунктуация перевода.
    words = text.split()
    if len(words) > 22 and "," not in text:
        # Очень длинную фразу без знаков всё же делим — но по границе
        # придаточного, а не посередине.
        for conj in (" porque ", " pero ", " aunque ", " cuando "):
            if conj in text:
                text = text.replace(conj, "," + conj, 1)
                break
    # 2) Завершаем точкой (уже есть) — но если фраза короче 3 слов,
    #    добавляем «!» для живости.
    if len(words) <= 3 and text.endswith("."):
        text = text[:-1] + "!"
    return text


def describe(text: str) -> tuple[str, dict]:
    """(тон, параметры) для текста — удобно для логов и тестов."""
    tone = detect_tone(text)
    return tone, params_for_tone(tone)


if __name__ == "__main__":
    import sys

    samples = [
        "Хрень твою, ты чё творишь?",
        "Eres un maldito cabron",
        "Привет, рад тебя видеть, брат!",
        "Hola, gracias por venir, amigo",
        "Как круто, все отлично",
        "!!!",
        "Хорошо, договорились",
    ]
    for s in samples:
        tone, p = describe(s)
        print(f"  {TONE_NAMES[tone]:<12} temp={p['temperature']:.2f} "
              f"speed={p['speed']:.2f}  {s!r}")
