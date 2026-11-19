"""Каталог моделей и языковых пакетов RedZ Voice Studio.

Единый источник правды для движка (tools/live_translate.py) и интерфейса:
что за модели существуют, какие языки они покрывают, какие направления
перевода реально есть и из каких моделей состоит языковой пакет.

Важно: здесь НЕТ фиктивных вариантов. В `PAIRS` попадают только пары,
которые реально опубликованы в Helsinki-NLP (проверено запросами к
huggingface.co/api/models, 2026-11-16). Если пары нет напрямую, маршрут
строится через английский как язык-посредник — и это видно в описании.

Хранилище моделей — существующий кэш HuggingFace (`HF_HUB_CACHE`).
Отдельной системы хранения нет.

Разделяем три характеристики (их нельзя смешивать):
  1. языки распознавания (ASR);
  2. направления перевода (Translation);
  3. языки синтеза (TTS).
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Языки
# ---------------------------------------------------------------------------

# Языки, для которых строятся языковые пакеты (язык пользователя — ru).
LANG_TITLES: dict[str, str] = {
    "ru": "Русский",
    "en": "Английский",
    "es": "Испанский",
    "de": "Немецкий",
    "fr": "Французский",
    "it": "Итальянский",
    "pt": "Португальский",
    "zh": "Китайский",
    "ja": "Японский",
    "hi": "Хинди",
    "ar": "Арабский",
}

# Языки, которые понимает Whisper large-v3-turbo (общая мультиязычная ASR).
WHISPER_LANGS: set[str] = {
    "ru", "en", "es", "de", "fr", "it", "pt", "zh", "ja", "hi", "ar",
    "uk", "pl", "cs", "sk", "bg", "sr", "hr", "sl", "mk", "bs", "ro", "hu",
    "tr", "el", "nl", "da", "sv", "no", "fi", "et", "lv", "lt", "he", "fa",
    "bn", "ur", "ta", "th", "vi", "id", "ms", "tl", "ko", "ca", "gl",
}

# Языки XTTS-v2 (клонирование голоса). Китайский — только путунхуа (zh-cn),
# арабский — литературный; диалекты модель не различает.
XTTS_LANGS: set[str] = {
    "ru", "en", "es", "de", "fr", "it", "pt", "pl", "tr", "nl", "cs",
    "ar", "zh", "hu", "ko", "ja", "hi",
}

XTTS_LANG_CODES: dict[str, str] = {"zh": "zh-cn"}

# ---------------------------------------------------------------------------
# Направления перевода Helsinki-NLP/opus-mt (проверено на HF)
# ---------------------------------------------------------------------------

PAIRS: set[tuple[str, str]] = {
    ("en", "de"), ("en", "fr"), ("en", "it"), ("en", "zh"), ("en", "hi"),
    ("en", "ar"), ("en", "es"), ("en", "ru"),
    ("de", "en"), ("de", "fr"), ("de", "it"), ("de", "zh"), ("de", "ar"),
    ("de", "es"),
    ("fr", "en"), ("fr", "de"), ("fr", "ar"), ("fr", "es"), ("fr", "ru"),
    ("it", "en"), ("it", "de"), ("it", "fr"), ("it", "ar"), ("it", "es"),
    ("zh", "en"), ("zh", "de"), ("zh", "it"),
    ("ja", "en"), ("ja", "de"), ("ja", "fr"), ("ja", "it"), ("ja", "pt"),
    ("ja", "ar"), ("ja", "es"), ("ja", "ru"),
    ("hi", "en"),
    ("ar", "en"), ("ar", "de"), ("ar", "fr"), ("ar", "it"), ("ar", "es"),
    ("ar", "ru"),
    ("es", "en"), ("es", "de"), ("es", "fr"), ("es", "it"), ("es", "ar"),
    ("es", "ru"),
    ("ru", "en"), ("ru", "fr"), ("ru", "ar"), ("ru", "es"),
}

# Промежуточный язык для пар, у которых нет прямой модели.
PIVOT = "en"

# Снапшот opus-mt содержит и pytorch_model.bin, и tf_model.h5 (~295 МБ
# каждый). Это реальный объём загрузки, поэтому и показываем его.
MT_REPO_SIZE_MB = 600
ASR_SIZES_MB = {
    "mobiuslabsgmbh/faster-whisper-large-v3-turbo": 390,
    "Systran/faster-whisper-small": 480,
}
TTS_SIZE_MB = 1900


def repo_name(src: str, dst: str) -> str:
    return f"Helsinki-NLP/opus-mt-{src}-{dst}"


def route(src: str, dst: str) -> list[str] | None:
    """Модели перевода src -> dst (прямая пара или через английский).

    None — перевести нечем: такой пары нет и обходного пути тоже.
    Пустой список — перевод не нужен (языки совпадают).
    """
    src = (src or "").lower().strip()
    dst = (dst or "").lower().strip()
    if not src or not dst:
        return None
    if src == dst:
        return []
    if (src, dst) in PAIRS:
        return [repo_name(src, dst)]
    if src != PIVOT and dst != PIVOT and (src, PIVOT) in PAIRS \
            and (PIVOT, dst) in PAIRS:
        return [repo_name(src, PIVOT), repo_name(PIVOT, dst)]
    return None


def route_kind(src: str, dst: str) -> str:
    """'direct' | 'pivot' | 'none' — как строится маршрут."""
    chain = route(src, dst)
    if chain is None:
        return "none"
    if not chain:
        return "same"
    return "direct" if len(chain) == 1 else "pivot"


# ---------------------------------------------------------------------------
# Каталог моделей
# ---------------------------------------------------------------------------

ASR_MODELS: list[dict] = [
    {
        "id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "type": "asr",
        "name": "Whisper large-v3-turbo",
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "developer": "OpenAI Whisper / Mobius Labs (CT2)",
        "source": "huggingface.co",
        "description": "Мультиязычное распознавание со знаками препинания; "
                       "одна модель на все поддерживаемые языки.",
        "languages": sorted(WHISPER_LANGS),
        "license": "MIT",
        "size_mb": ASR_SIZES_MB["mobiuslabsgmbh/faster-whisper-large-v3-turbo"],
        "ram_mb": 1400,
        "vram_mb": 1020,
        "devices": ["CUDA", "CPU"],
    },
    {
        "id": "Systran/faster-whisper-small",
        "type": "asr",
        "name": "Whisper small (CT2)",
        "repo": "Systran/faster-whisper-small",
        "developer": "OpenAI Whisper / Systran (CT2)",
        "source": "huggingface.co",
        "description": "Лёгкая модель распознавания: быстрее и меньше VRAM, "
                       "но хуже пунктуация и полнота фраз.",
        "languages": sorted(WHISPER_LANGS),
        "license": "MIT",
        "size_mb": ASR_SIZES_MB["Systran/faster-whisper-small"],
        "ram_mb": 700,
        "vram_mb": 500,
        "devices": ["CUDA", "CPU"],
    },
]

TTS_MODELS: list[dict] = [
    {
        "id": "tts-hub/XTTS-v2",
        "type": "tts",
        "name": "XTTS v2 (клон голоса)",
        "repo": "tts-hub/XTTS-v2",
        "developer": "Coqui",
        "source": "huggingface.co",
        "description": "Синтез речи клонированным голосом пользователя. "
                       "Одна модель на все языки синтеза.",
        "languages": sorted(XTTS_LANGS),
        "license": "Coqui Public Model License (некоммерческая)",
        "size_mb": TTS_SIZE_MB,
        "ram_mb": 2600,
        "vram_mb": 2400,
        "devices": ["CUDA", "CPU"],
    },
]


def mt_models() -> list[dict]:
    """Модели перевода, которые нужны для пользователя с языком ru.

    Показываем только те пары, что реально опубликованы (PAIRS), включая
    обратные направления: без них не переводится речь собеседника.
    """
    out: list[dict] = []
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for code in LANG_TITLES:
        if code == "ru":
            continue
        if (code, "ru") in PAIRS:
            pairs.append((code, "ru"))
        if ("ru", code) in PAIRS:
            pairs.append(("ru", code))
    for src, dst in pairs:
        repo = repo_name(src, dst)
        if repo in seen:
            continue
        seen.add(repo)
        out.append({
            "id": repo,
            "type": "mt",
            "name": repo.split("/")[-1],
            "repo": repo,
            "developer": "Helsinki-NLP (Marian / OPUS)",
            "source": "huggingface.co",
            "description": f"Перевод {LANG_TITLES[src].lower()} → "
                           f"{LANG_TITLES[dst].lower()}.",
            "direction": f"{src}->{dst}",
            "languages": [src, dst],
            "license": "CC-BY-4.0",
            "size_mb": MT_REPO_SIZE_MB,
            "ram_mb": 700,
            "vram_mb": 0,
            "devices": ["CPU", "CUDA"],
        })
    return out


def discovered() -> list[dict]:
    """Модели из обновляемого каталога HuggingFace (если он уже собран)."""
    try:
        import model_discovery
        return [m for m in model_discovery.load_models() if m.get("id")]
    except Exception:
        return []


def catalog() -> list[dict]:
    """Полный каталог: проверенные ASR + MT + TTS плюс найденные на HF.

    Проверенные записи идут первыми и не дублируются: у них точные
    требования, проверенные замером.
    """
    base = list(ASR_MODELS) + mt_models() + list(TTS_MODELS)
    seen = {m["id"] for m in base}
    extra = [m for m in discovered() if m.get("id") not in seen]
    return base + extra


def model_by_id(model_id: str) -> dict | None:
    for item in catalog():
        if item["id"] == model_id:
            return item
    return None


def models_for_kind(kind: str) -> list[dict]:
    return [m for m in catalog() if m["type"] == kind]


# ---------------------------------------------------------------------------
# Языковые пакеты
# ---------------------------------------------------------------------------

def _unique(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def language_pack(code: str, user_lang: str = "ru") -> dict:
    """Что нужно, чтобы полноценно говорить с языком `code`.

    Пакет описывает зависимости, а не копии моделей: общая ASR-модель и
    язык-посредник en переиспользуются всеми пакетами.
    """
    code = (code or "").lower().strip()
    title = LANG_TITLES.get(code, code)
    to_user = route(code, user_lang) or []
    from_user = route(user_lang, code) or []
    repos = _unique(to_user + from_user)

    asr = ASR_MODELS[0]["repo"]
    tts = TTS_MODELS[0]["repo"]
    tts_code = XTTS_LANG_CODES.get(code, code)

    return {
        "code": code,
        "title": title,
        "asr_supported": code in WHISPER_LANGS,
        "tts_supported": code in XTTS_LANGS,
        "tts_language": tts_code,
        "to_user": {"lang": user_lang, "models": to_user,
                    "kind": route_kind(code, user_lang)},
        "from_user": {"lang": code, "models": from_user,
                      "kind": route_kind(user_lang, code)},
        "models": repos,
        # общие модели (одна ASR и одна TTS на все пакеты)
        "shared_models": [asr, tts],
        "size_mb": sum(MT_REPO_SIZE_MB for _ in repos),
        "note": "" if route_kind(code, user_lang) != "none"
                else "нет прямого перевода на русский и через английский",
    }


def all_packs(user_lang: str = "ru") -> list[dict]:
    return [language_pack(code, user_lang)
            for code in LANG_TITLES if code != user_lang]


# ---------------------------------------------------------------------------
# Проверка установленности (общая с движком)
# ---------------------------------------------------------------------------

def hf_hub_dir() -> str:
    return os.environ.get("HF_HUB_CACHE") or os.path.expanduser(
        os.path.join("~", ".cache", "huggingface", "hub"))


WEIGHT_SUFFIXES = (".bin", ".safetensors", ".pth", ".onnx", ".h5",
                   ".ckpt")


def installed(name: str) -> bool:
    """Есть ли модель на диске целиком (ничего не скачивает).

    Недостаточно наличия каталога snapshot: отменённая или оборванная
    загрузка оставляет пустой/частичный снапшот. Проверяем, что в нём
    есть хотя бы один файл с весами — тогда модель можно загрузить.
    """
    if not name:
        return False
    if os.path.isdir(name):
        try:
            return any(f.endswith(WEIGHT_SUFFIXES)
                       for _r, _d, fs in os.walk(name) for f in fs)
        except Exception:
            return False
    base = os.path.join(hf_hub_dir(), "models--" + name.replace("/", "--"))
    snaps = os.path.join(base, "snapshots")
    if not os.path.isdir(snaps):
        return False
    for rev in os.listdir(snaps):
        folder = os.path.join(snaps, rev)
        try:
            files = os.listdir(folder)
        except OSError:
            continue
        if any(f.endswith(WEIGHT_SUFFIXES) for f in files):
            return True
    return False


def disk_size_mb(name: str) -> float:
    """Сколько занимает модель в кэше (МБ).

    Считаем только `blobs`: на Windows HuggingFace раскладывает файлы в
    snapshots копиями, и обход всего каталога удваивает (а с несколькими
    ревизиями — утраивает) размер. Объём blobs — это ровно то, что
    скачано, и с ним сравнивается прогресс загрузки.
    """
    base = os.path.join(hf_hub_dir(), "models--" + name.replace("/", "--"),
                        "blobs")
    total = 0
    for root, _dirs, files in os.walk(base):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024.0 * 1024.0), 1)
