"""Обновляемый каталог моделей с HuggingFace.

Зачем: статический список в model_registry — только проверенные модели,
которые движок гарантированно умеет готовить. Пользователь должен видеть и
другие опубликованные репозитории: сколько весят, сколько просят RAM/VRAM и
влезут ли они вместе с игрой.

Модуль ничего не скачивает: только читает публичный API HuggingFace
(`/api/models`) и складывает результат в workspace/models_discovered.json.
Движок и интерфейс читают этот же файл через model_registry.catalog().

Никаких тяжёлых зависимостей: urllib + concurrent.futures.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://huggingface.co/api/models"
CACHE_NAME = "models_discovered.json"
HTTP_TIMEOUT = 25

# Пары opus-mt: Helsinki-NLP/opus-mt-<src>-<dst>
_MT_RE = re.compile(r"^Helsinki-NLP/opus-mt-([a-z]{2,3})-([a-z]{2,3})$")

# Оценка ресурсов для CT2-сборок Whisper (RAM МБ, VRAM МБ на int8_float16).
# turbo — по замеру проекта (1020 МБ VRAM), остальные — по размеру весов.
_WHISPER_HW = {
    "tiny": (300, 150),
    "base": (450, 250),
    "small": (700, 500),
    "medium": (2000, 1400),
    "large": (3500, 2800),
    "turbo": (1400, 1020),
}


def workspace() -> str:
    """Рабочая папка приложения (та же, что у studio_paths)."""
    ws = os.environ.get("AURALOOM_WORKSPACE")
    if ws:
        return ws
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Auraloom", "workspace")


def cache_path() -> str:
    return os.path.join(workspace(), CACHE_NAME)


def _http_json(url: str) -> dict | list | None:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Auraloom/1.0 (model catalog)"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _license_of(info: dict) -> str:
    tags = info.get("tags") or []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("license:"):
            return tag.split(":", 1)[1]
    card = info.get("cardData") or {}
    if isinstance(card, dict) and card.get("license"):
        return str(card["license"])
    return "не указана"


def _size_mb(info: dict) -> float:
    used = info.get("usedStorage")
    if isinstance(used, (int, float)) and used > 0:
        return round(float(used) / (1024.0 * 1024.0), 1)
    sib = info.get("siblings") or []
    total = sum((s.get("size") or 0) for s in sib if isinstance(s, dict))
    return round(total / (1024.0 * 1024.0), 1)


def _canon(code: str) -> str:
    """Нормализовать код языка из имени модели (jpn/zh -> короткий)."""
    aliases = {
        "jap": "ja", "jpn": "ja", "zho": "zh", "chi": "zh", "zh-cn": "zh",
        "eng": "en", "spa": "es", "rus": "ru", "deu": "de", "fra": "fr",
        "ita": "it", "por": "pt",
    }
    return aliases.get(code, code)


def _whisper_entry(info: dict) -> dict:
    repo = str(info.get("id", ""))
    low = repo.lower()
    size_mb = _size_mb(info)
    kind = ""
    for key in ("large-v3", "large", "medium", "small", "base", "tiny"):
        if key in low:
            kind = "large" if key == "large-v3" else key
            break
    if "turbo" in low:
        # turbo — отдельная ветка: маленькие веса, но качество large
        kind = "turbo"
    ram, vram = _WHISPER_HW.get(kind, (max(700, int(size_mb * 2.2)),
                                      max(300, int(size_mb * 1.6))))
    name = repo.split("/")[-1].replace("faster-whisper-", "Whisper ")
    if kind:
        name = "Whisper " + (kind if kind != "large" else "large")
        if "turbo" in low:
            name = "Whisper large-v3-turbo"
        name += " (CT2)"
    return {
        "id": repo,
        "type": "asr",
        "name": name,
        "repo": repo,
        "developer": str(info.get("author") or "community"),
        "source": "huggingface.co",
        "description": "Сборка Whisper в CTranslate2: ставится faster-whisper. "
                       + ("Мультиязычная." if ".en" not in low else "Только английский."),
        "languages": [] if ".en" not in low else ["en"],
        "license": _license_of(info),
        "size_mb": size_mb,
        "ram_mb": ram,
        "vram_mb": vram,
        "devices": ["CUDA", "CPU"],
        "downloads": int(info.get("downloads") or 0),
        "discovered": True,
    }


def _mt_entry(info: dict, src: str, dst: str) -> dict:
    repo = str(info.get("id", ""))
    return {
        "id": repo,
        "type": "mt",
        "name": repo.split("/")[-1],
        "repo": repo,
        "developer": "Helsinki-NLP (Marian / OPUS)",
        "source": "huggingface.co",
        "description": f"Перевод {src} → {dst}.",
        "direction": f"{src}->{dst}",
        "languages": [src, dst],
        "license": _license_of(info),
        "size_mb": _size_mb(info),
        "ram_mb": 700,
        "vram_mb": 0,
        "devices": ["CPU", "CUDA"],
        "downloads": int(info.get("downloads") or 0),
        "discovered": True,
    }


def _details(repo: str) -> dict:
    data = _http_json(f"{API}/{urllib.parse.quote(repo)}?blobs=true")
    return data if isinstance(data, dict) else {"id": repo}


def refresh(user_lang: str = "ru", asr_limit: int = 16) -> dict:
    """Опросить HF и обновить кэш. Возвращает {'ok', 'found', 'asr', 'mt'}."""
    user_lang = (user_lang or "ru").strip().lower()

    mt_repos: list[str] = []
    listed = _http_json(f"{API}?author=Helsinki-NLP&search=opus-mt&limit=1000")
    if isinstance(listed, list):
        for item in listed:
            repo = str((item or {}).get("id", ""))
            m = _MT_RE.match(repo)
            if not m:
                continue
            src, dst = _canon(m.group(1)), _canon(m.group(2))
            if user_lang in (src, dst):
                mt_repos.append(repo)

    asr_repos: list[str] = []
    listed = _http_json(
        f"{API}?search=faster-whisper&limit=80&sort=downloads&direction=-1")
    if isinstance(listed, list):
        for item in listed:
            repo = str((item or {}).get("id", ""))
            low = repo.lower()
            if "faster-whisper" not in low and "whisper" not in low:
                continue
            if int((item or {}).get("downloads") or 0) < 300:
                continue
            asr_repos.append(repo)
            if len(asr_repos) >= asr_limit:
                break

    repos = list(dict.fromkeys(mt_repos + asr_repos))
    details: dict[str, dict] = {}
    if repos:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for info in pool.map(_details, repos):
                repo = str(info.get("id", ""))
                if repo:
                    details[repo] = info

    models: list[dict] = []
    for repo in mt_repos:
        info = details.get(repo) or {}
        m = _MT_RE.match(repo)
        if m:
            models.append(_mt_entry(info, _canon(m.group(1)), _canon(m.group(2))))
    for repo in asr_repos:
        models.append(_whisper_entry(details.get(repo) or {"id": repo}))

    data = {
        "updated": int(time.time()),
        "user_lang": user_lang,
        "models": models,
    }
    path = cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "found": 0, "asr": 0, "mt": 0,
                "error": f"не записался кэш: {exc}"}
    return {"ok": bool(models), "found": len(models),
            "asr": len(asr_repos), "mt": len(mt_repos),
            "updated": data["updated"]}


# --------------------------------------------------------------------------
# Чтение кэша (используется model_registry)
# --------------------------------------------------------------------------
_cache: dict = {"mtime": None, "models": []}


def load() -> dict:
    """Содержимое кэша: {'updated': int, 'models': [...]}. Без сети."""
    path = cache_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {"updated": 0, "models": []}
    if _cache["mtime"] == mtime:
        return {"updated": _cache.get("updated", 0),
                "models": list(_cache["models"])}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        models = [m for m in (data.get("models") or []) if isinstance(m, dict)]
        _cache.update({"mtime": mtime, "models": models,
                       "updated": int(data.get("updated") or 0)})
        return {"updated": int(data.get("updated") or 0), "models": models}
    except Exception:
        return {"updated": 0, "models": []}


def load_models() -> list[dict]:
    return load()["models"]
