"""Пути, рабочая папка и поиск движка для Auraloom.

Приложение работает и как EXE, и из исходников. Всё состояние лежит в
%LOCALAPPDATA%\\RedZVoiceStudio\\workspace, чтобы не зависеть от того,
откуда запущено приложение.
"""

from __future__ import annotations

import os
import sys
import time

import branding

# Папка данных берётся из branding.py: при ребрендинге меняется одно имя,
# а существующая папка переименовывается (ниже), чтобы не потерять модели
# и настройки.
APP_NAME = branding.DATA_DIR
PIPER_VOICES = {
    "M": ("es_MX-ald-medium.onnx", "es_MX-ald-medium.onnx.json"),
    "F": ("es_MX-claude-high.onnx", "es_MX-claude-high.onnx.json"),
}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> str:
    """Папка с ресурсами: временная при сборке в EXE, иначе корень проекта."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # из исходников app/ лежит рядом с корнем проекта
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def single_instance_lock() -> bool:
    """Не дать открыть приложение дважды.

    Два экземпляра делят одну рабочую папку: один перетирает файлы другого
    (список фраз, озвучка) и получает PermissionError. Возвращает True,
    если запуск разрешён (эксклюзивная блокировка файла в Windows).
    """
    path = os.path.join(local_app_data(), "app.lock")
    try:
        fh = open(path, "a+b")
    except Exception:
        return True  # не смогли создать файл — не блокируем запуск
    try:
        fh.seek(0)
        fh.write(b"0")
        fh.flush()
        fh.seek(0)
        import msvcrt
        # LK_NBLCK: эксклюзивная блокировка, не ждать
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except Exception:
        try:
            fh.close()
        except Exception:
            pass
        return False  # уже запущен другой экземпляр
    # держим файл открытым, пока работает приложение
    _LOCK_HANDLE.append(fh)
    return True


_LOCK_HANDLE: list = []


def app_dir() -> str:
    """Куда ставить EXE / откуда запускать."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def local_app_data() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return _migrate_data_dir(base, os.path.join(base, APP_NAME))


def _migrate_data_dir(base: str, target: str) -> str:
    """Переименовать старую папку данных после смены названия.

    Возвращает папку, в которой реально надо работать. Если переименование
    не удалось (Windows держит файлы — запущен движок), возвращаем старую
    папку: иначе приложение стартовало бы с пустым workspace и «потеряло»
    модели и настройки.
    """
    if os.path.isdir(target):
        return target
    for old in getattr(branding, "LEGACY_DATA_DIRS", ()) or ():
        src = os.path.join(base, old)
        if not os.path.isdir(src):
            continue
        try:
            os.replace(src, target)
            return target
        except Exception:
            return src
    return target


def workspace() -> str:
    """Рабочая папка: lines.json, out/, sounds/, player/, voice_samples/."""
    path = os.path.join(local_app_data(), "workspace")
    ensure_workspace(path)
    return path


def engine_dir() -> str:
    """Папка с движком. Сначала ищется рядом с EXE (в RedZVoiceStudio_Data/engine/),
    затем в %LOCALAPPDATA%."""
    app_dir_path = app_dir()
    engine_next_to_exe = os.path.join(app_dir_path, "engine")
    if os.path.isdir(engine_next_to_exe):
        return engine_next_to_exe
    return os.path.join(local_app_data(), "engine")


def engine_python() -> str | None:
    """Python движка (с torch/coqui-tts). None — если движка нет."""
    candidates = [
        os.path.join(engine_dir(), "Scripts", "python.exe"),
        os.path.join(engine_dir(), "bin", "python"),
        os.environ.get("REDZ_ENGINE_PYTHON", ""),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def ensure_workspace(path: str) -> None:
    for sub in ("out", "out/wav", "out/ogg", "out/mp3", "sounds", "player",
                "player/mp3", "voice_samples", "logs"):
        os.makedirs(os.path.join(path, sub.replace("/", os.sep)), exist_ok=True)


def _safe_copy(src: str, dst: str) -> bool:
    """Копирование, не падающее из-за блокировки файла.

    ВАЖНО: shutil.copy2 переносит АТРИБУТЫ файла. Файлы в бандле PyInstaller
    (_MEIPASS) помечены «только чтение», и copy2 на них падает с
    PermissionError — правки движка не доезжали до рабочей папки.
    Поэтому копируем обычным чтением/записью, без атрибутов.
    """
    try:
        with open(src, "rb") as fin:
            data = fin.read()
        with open(dst, "wb") as fout:
            fout.write(data)
        # снять «только чтение» с цели, если она была
        try:
            os.chmod(dst, 0o666)
        except OSError:
            pass
        return True
    except (PermissionError, OSError) as exc:
        try:
            logs = os.path.join(local_app_data(), "workspace", "logs")
            os.makedirs(logs, exist_ok=True)
            with open(os.path.join(logs, "tools_update.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(f"  не скопирован {os.path.basename(dst)}: "
                         f"{type(exc).__name__}: {exc}\n")
        except Exception:
            pass
        return False


def seed_workspace() -> None:
    """Скопировать в рабочую папку lines.json, плеер и голоса Piper."""
    ws = workspace()
    src = resource_dir()

    lines_src = os.path.join(src, "lines.json")
    if os.path.exists(lines_src):
        dst = os.path.join(ws, "lines.json")
        if not os.path.exists(dst) or os.path.getmtime(lines_src) > os.path.getmtime(dst):
            _safe_copy(lines_src, dst)

    # Плеер
    player_src = os.path.join(src, "player", "index.html")
    if os.path.exists(player_src):
        os.makedirs(os.path.join(ws, "player"), exist_ok=True)
        _safe_copy(player_src, os.path.join(ws, "player", "index.html"))

    # Голоса Piper (es-MX) — нужны для офлайн-озвучки
    voices_dir = os.path.join(ws, "voices")
    os.makedirs(voices_dir, exist_ok=True)
    for key, (onnx, cfg) in PIPER_VOICES.items():
        for fname in (onnx, cfg):
            src_f = os.path.join(src, "voices", fname)
            if not os.path.exists(src_f):
                src_f = os.path.join(src, fname)
            if os.path.exists(src_f):
                _safe_copy(src_f, os.path.join(voices_dir, fname))

    # Готовые звуковые подсказки (образцы интонации) — уже записанные
    # WAV из voices/prompts. Копируются в рабочую папку, чтобы их
    # можно было слушать и из EXE, и из исходников.
    prompts_src = os.path.join(src, "voices", "prompts")
    prompts_dst = os.path.join(voices_dir, "prompts")
    if os.path.isdir(prompts_src):
        os.makedirs(prompts_dst, exist_ok=True)
        for fname in os.listdir(prompts_src):
            s = os.path.join(prompts_src, fname)
            if not os.path.isfile(s):
                continue
            d = os.path.join(prompts_dst, fname)
            if (not os.path.exists(d)
                    or os.path.getsize(s) != os.path.getsize(d)):
                _safe_copy(s, d)
    else:
        # В бандле PyInstaller путь может быть voices/prompts сразу в корне
        alt = os.path.join(src, "prompts")
        if os.path.isdir(alt):
            os.makedirs(prompts_dst, exist_ok=True)
            for fname in os.listdir(alt):
                s = os.path.join(alt, fname)
                if os.path.isfile(s):
                    _safe_copy(s, os.path.join(prompts_dst, fname))


def tool_path(name: str) -> str:
    """Путь к CLI-инструменту: рядом с EXE (tools/) или в исходниках."""
    for base in (app_dir(), resource_dir()):
        p = os.path.join(base, "tools", name)
        if os.path.exists(p):
            return p
    return os.path.join(app_dir(), "tools", name)


def _same_content(a: str, b: str) -> bool:
    """Одинаково ли содержимое двух файлов (быстро, по размеру и хэшу)."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                ca, cb = fa.read(65536), fb.read(65536)
                if ca != cb:
                    return False
                if not ca:
                    return True
    except OSError:
        return False


def workspace_tools() -> str:
    """Папка, куда копировать CLI-инструменты для вызова из EXE.

    Кроме копирования новых/изменённых файлов удаляет осиротевшие копии:
    скрипты, которых больше нет в источнике (например, после переноса
    одноразовых скриптов в tools/archive). Иначе в рабочей папке остаются
    копии удалённой функциональности, и приложение может вызвать старый
    скрипт вместо отсутствующего.
    """
    ws = workspace()
    dst = os.path.join(ws, "tools")
    os.makedirs(dst, exist_ok=True)
    # В собранном EXE инструменты лежат в бандле (resource_dir/tools),
    # в исходниках — рядом с app/ (app_dir/tools).
    for base in (resource_dir(), app_dir()):
        src_tools = os.path.join(base, "tools")
        if not os.path.isdir(src_tools):
            _log_tools_update(src_tools + " (НЕТ ПАПКИ)", -1)
            continue
        copied = 0
        src_names: set[str] = set()
        for fname in os.listdir(src_tools):
            if fname.endswith((".py", ".ps1")):
                src_names.add(fname)
                source = os.path.join(src_tools, fname)
                target = os.path.join(dst, fname)
                # Копируем, если файла нет ИЛИ содержимое отличается.
                # Раньше было «только если нет» — тогда правки движка
                # (live_translate.py) НИКОГДА не доходили до рабочей папки,
                # и приложение молча работало на старой версии.
                # Сверяем содержимое, а не время: в EXE время извлечения
                # файлов произвольное, и по mtime обновление терялось.
                if os.path.exists(target) and _same_content(source, target):
                    continue
                # _safe_copy копирует обычным чтением/записью: shutil.copy2
                # переносит атрибут «только чтение» из бандла PyInstaller
                # и на нём падает (PermissionError)
                if _safe_copy(source, target):
                    copied += 1
        # Осиротевшие копии: файл есть в рабочей папке, но его больше нет
        # в источнике. Удаляем только файлы .py/.ps1 (не папки и не данные),
        # сбой удаления не должен ломать запуск.
        removed = 0
        for fname in os.listdir(dst):
            if not fname.endswith((".py", ".ps1")) or fname in src_names:
                continue
            target = os.path.join(dst, fname)
            if not os.path.isfile(target):
                continue
            try:
                os.remove(target)
                removed += 1
            except OSError:
                pass
        _log_tools_update(src_tools, copied, removed)
        break
    return dst


def _log_tools_update(src_tools: str, copied: int, removed: int = 0) -> None:
    """Записать в журнал, откуда и сколько инструментов обновлено/убрано."""
    try:
        logs = os.path.join(local_app_data(), "workspace", "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "tools_update.log"), "a",
                  encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} frozen={is_frozen()} "
                     f"источник={src_tools} "
                     f"существует={os.path.isdir(src_tools)} "
                     f"обновлено={copied} удалено={removed}\n")
    except Exception:
        pass


def output_paths() -> dict[str, str]:
    ws = workspace()
    return {
        "workspace": ws,
        "out_wav": os.path.join(ws, "out", "wav"),
        "out_ogg": os.path.join(ws, "out", "ogg"),
        "out_mp3": os.path.join(ws, "out", "mp3"),
        "sounds": os.path.join(ws, "sounds"),
        "player_mp3": os.path.join(ws, "player", "mp3"),
        "samples": os.path.join(ws, "voice_samples"),
        "reference": os.path.join(ws, "reference.wav"),
        "lines": os.path.join(ws, "lines.json"),
        # профили клонированного голоса
        "profiles": os.path.join(ws, "voice_profiles"),
    }


# --------------------------------------------------------------------------
# Профили голоса (несколько клонов одного голоса)
# --------------------------------------------------------------------------
def profiles_dir() -> str:
    """Папка профилей: workspace/voice_profiles."""
    d = os.path.join(workspace(), "voice_profiles")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def profile_dir(name: str) -> str:
    """Папка конкретного профиля."""
    return os.path.join(profiles_dir(), _safe_name(name))


def profile_reference(name: str) -> str:
    """reference.wav конкретного профиля."""
    return os.path.join(profile_dir(name), "reference.wav")


def _safe_name(name: str) -> str:
    """Имя профиля -> безопасное имя папки."""
    keep = []
    for ch in (name or "").strip():
        if ch.isalnum() or ch in " _-":
            keep.append(ch)
        elif ch in "ёйцукенгшщзхъфывапролджэячсмитьбю":
            keep.append(ch)
    out = "".join(keep).strip().replace(" ", "_")
    return out or "profile"


def list_profiles() -> list[str]:
    """Список профилей.

    Показываем и пустые (только что созданные) — иначе созданный профиль
    не появляется в комбобоксе, пока в нём нет reference.wav.
    """
    d = profiles_dir()
    out: list[str] = []
    try:
        for entry in sorted(os.listdir(d)):
            p = os.path.join(d, entry)
            if os.path.isdir(p):
                out.append(entry)
    except Exception:
        pass
    return out


def create_profile(name: str) -> tuple[str, str]:
    """Создать профиль. Возвращает (путь_к_reference, сообщение)."""
    d = profile_dir(name)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as exc:
        return "", f"не удалось создать профиль: {exc}"
    ref = os.path.join(d, "reference.wav")
    if os.path.exists(ref):
        return ref, f"профиль «{name}» уже существует"
    return ref, f"профиль «{name}» создан"


def active_profile_file() -> str:
    """Файл с именем активного профиля."""
    return os.path.join(workspace(), "active_profile.txt")


def get_active_profile() -> str:
    """Имя активного профиля (пустая строка — используется общий reference.wav)."""
    try:
        with open(active_profile_file(), encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def set_active_profile(name: str) -> None:
    """Запомнить активный профиль."""
    try:
        with open(active_profile_file(), "w", encoding="utf-8") as fh:
            fh.write((name or "").strip())
    except Exception:
        pass


def active_reference() -> str:
    """Путь к reference активного профиля.

    Если профиль выбран — возвращаем его reference.wav (даже если файла
    ещё нет: сборка создаст его там). Иначе — общий reference.wav.
    """
    name = get_active_profile()
    if name:
        return profile_reference(name)
    return output_paths()["reference"]
