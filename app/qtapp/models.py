"""QAbstractListModel-обёртки для QML: голоса (запись/подсказки/образцы) и история.

Модели отдают данные в QML через `roleNames()`. Логика записи и клонирования —
в существующих модулях (studio_core, prompt_library, ui.audio_play).
"""

from __future__ import annotations

import os
import time

from PySide6.QtCore import (QAbstractListModel, QObject, Signal, Slot,
                            Property, QModelIndex, Qt)

import studio_paths as sp
import studio_core as core
import prompt_library as plib


# ======================================================================
# Модель подсказок (список фраз)
# ======================================================================
class PromptModel(QAbstractListModel):
    """Плоский список подсказок с фильтром по эмоции."""

    PromptRole = Qt.UserRole + 1
    RuRole = Qt.UserRole + 2
    EsRole = Qt.UserRole + 3
    EmotionRole = Qt.UserRole + 4
    EmotionLabelRole = Qt.UserRole + 5
    DurationRole = Qt.UserRole + 6
    OkRole = Qt.UserRole + 7

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self._filter = ""
        self.reload()

    def roleNames(self) -> dict:
        return {
            self.PromptRole: b"prompt",
            self.RuRole: b"ru",
            self.EsRole: b"es",
            self.EmotionRole: b"emotion",
            self.EmotionLabelRole: b"emotion_label",
            self.DurationRole: b"duration",
            self.OkRole: b"ok",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == self.PromptRole:
            return item.get("index", index.row())
        if role == self.RuRole:
            return item.get("ru", "")
        if role == self.EsRole:
            return item.get("es", "")
        if role == self.EmotionRole:
            return item.get("emotion", "")
        if role == self.EmotionLabelRole:
            return item.get("emotion_label", "")
        if role == self.DurationRole:
            return float(item.get("duration", 0.0) or 0.0)
        if role == self.OkRole:
            return bool(item.get("ok", False))
        return None

    def reload(self) -> None:
        self.beginResetModel()
        try:
            items = [dict(x) for x in plib.manifest()]
        except Exception:
            items = []
        # отметки «записано»
        records = _load_records()
        for it in items:
            it["ok"] = int(it.get("index", -1)) in records
        self._items = [it for it in items if self._matches(it)]
        self.endResetModel()

    def _matches(self, item: dict) -> bool:
        if not self._filter:
            return True
        return str(item.get("emotion", "")) == self._filter

    @Slot(str)
    def setFilter(self, emotion: str) -> None:
        if self._filter == (emotion or ""):
            return
        self._filter = emotion or ""
        self.reload()

    @Slot(int, result="QVariant")
    def itemAt(self, row: int):
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    @Slot(result=int)
    def count(self) -> int:
        return len(self._items)


# ======================================================================
# Модель дублей (таблица прогресса записи)
# ======================================================================
class TakeModel(QAbstractListModel):
    """Прогресс записи: какие подсказки уже записаны."""

    IndexRole = Qt.UserRole + 1
    TextRole = Qt.UserRole + 2
    EmotionRole = Qt.UserRole + 3
    EmotionLabelRole = Qt.UserRole + 4
    DurationRole = Qt.UserRole + 5
    OkRole = Qt.UserRole + 6

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self.reload()

    def roleNames(self) -> dict:
        return {
            self.IndexRole: b"index",
            self.TextRole: b"text",
            self.EmotionRole: b"emotion",
            self.EmotionLabelRole: b"emotion_label",
            self.DurationRole: b"duration",
            self.OkRole: b"ok",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        it = self._items[index.row()]
        if role == self.IndexRole:
            return it.get("index", index.row())
        if role == self.TextRole:
            return it.get("text", "")
        if role == self.EmotionRole:
            return it.get("emotion", "")
        if role == self.EmotionLabelRole:
            return it.get("emotion_label", "")
        if role == self.DurationRole:
            return float(it.get("duration", 0.0) or 0.0)
        if role == self.OkRole:
            return bool(it.get("ok", False))
        return None

    def reload(self) -> None:
        self.beginResetModel()
        records = _load_records()
        items = []
        try:
            manifest = plib.manifest()
        except Exception:
            manifest = []
        for it in manifest:
            idx = int(it.get("index", 0))
            path = records.get(idx, "")
            dur = 0.0
            if path and os.path.exists(path):
                try:
                    import soundfile as sf
                    info = sf.info(path)
                    dur = float(info.duration)
                except Exception:
                    dur = 0.0
            items.append({
                "index": idx,
                "text": it.get("es", ""),
                "emotion": it.get("emotion", ""),
                "emotion_label": it.get("emotion_label", ""),
                "duration": dur,
                "ok": bool(path),
            })
        self._items = items
        self.endResetModel()

    @Slot(result=int)
    def count(self) -> int:
        return len(self._items)

    @Slot(result=int)
    def doneCount(self) -> int:
        return sum(1 for it in self._items if it.get("ok"))


# ======================================================================
# Модель образцов (готовые дубли)
# ======================================================================
class SampleModel(QAbstractListModel):
    """Список записанных дублей в workspace/voice_samples."""

    PathRole = Qt.UserRole + 1
    NameRole = Qt.UserRole + 2
    MetaRole = Qt.UserRole + 3
    DurationRole = Qt.UserRole + 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self.reload()

    def roleNames(self) -> dict:
        return {
            self.PathRole: b"path",
            self.NameRole: b"name",
            self.MetaRole: b"meta",
            self.DurationRole: b"duration",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        it = self._items[index.row()]
        if role == self.PathRole:
            return it.get("path", "")
        if role == self.NameRole:
            return it.get("name", "")
        if role == self.MetaRole:
            return it.get("meta", "")
        if role == self.DurationRole:
            return float(it.get("duration", 0.0) or 0.0)
        return None

    def reload(self) -> None:
        self.beginResetModel()
        items = []
        d = sp.output_paths()["samples"]
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if not fn.lower().endswith(".wav"):
                    continue
                p = os.path.join(d, fn)
                dur = 0.0
                try:
                    import soundfile as sf
                    dur = float(sf.info(p).duration)
                except Exception:
                    pass
                items.append({
                    "path": p,
                    "name": fn,
                    "meta": f"{dur:.1f} c" if dur else "—",
                    "duration": dur,
                })
        self._items = items
        self.endResetModel()

    @Slot(result=int)
    def count(self) -> int:
        return len(self._items)


# ======================================================================
# Модель истории переводов
# ======================================================================
# История переживает перезапуск (ROADMAP 8.3–8.4): простой jsonl в рабочей
# папке. Старше HISTORY_RETENTION_DAYS отбрасываем при загрузке и сразу же
# переписываем файл — логи не растут бесконечно.
HISTORY_RETENTION_DAYS = 3


def history_path() -> str:
    return os.path.join(sp.workspace(), "history.jsonl")


class HistoryModel(QAbstractListModel):
    """История переводов за последние 3 дня, новые записи — сверху."""

    RuRole = Qt.UserRole + 1
    EsRole = Qt.UserRole + 2
    DirRole = Qt.UserRole + 3
    TimeRole = Qt.UserRole + 4

    def __init__(self, parent=None, path: str | None = None) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self._path = path or history_path()
        self._load()

    def roleNames(self) -> dict:
        return {
            self.RuRole: b"ru",
            self.EsRole: b"es",
            self.DirRole: b"dir",
            self.TimeRole: b"time",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        it = self._items[index.row()]
        if role == self.RuRole:
            return it["ru"]
        if role == self.EsRole:
            return it["es"]
        if role == self.DirRole:
            return it["dir"]
        if role == self.TimeRole:
            return it["time"]
        return None

    # ---------- хранение ----------
    def _load(self) -> None:
        """Прочитать историю с диска и отбросить устаревшее.

        В памяти записи идут от свежих к старым, поэтому в списках свежая
        реплика оказывается сверху, а старые — ниже.
        """
        import json
        cutoff = time.time() - HISTORY_RETENTION_DAYS * 86400
        rows: list[dict] = []
        dropped = False
        try:
            with open(self._path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        it = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(it, dict) or not it.get("ru"):
                        continue
                    ts = float(it.get("ts") or 0)
                    if ts and ts < cutoff:
                        dropped = True
                        continue
                    rows.append({
                        "ru": it["ru"],
                        "es": it.get("es") or "—",
                        "dir": "out" if it.get("dir") == "out" else "in",
                        "ts": ts,
                        "time": time.strftime("%H:%M:%S", time.localtime(ts))
                        if ts else str(it.get("time") or ""),
                    })
        except FileNotFoundError:
            return
        except Exception:  # noqa: BLE001
            return
        if len(rows) > 500:
            rows = rows[-500:]
            dropped = True
        rows.reverse()
        self.beginResetModel()
        self._items = rows
        self.endResetModel()
        if dropped:
            # чистка на диске: просроченные строки в файле больше не нужны
            self._rewrite_file()

    def _append_file(self, item: dict) -> None:
        import json
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": item["ts"], "dir": item["dir"],
                    "ru": item["ru"], "es": item["es"],
                }, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def _rewrite_file(self) -> None:
        import json
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            # в памяти «свежие сверху», а в файле держим хронологию
            with open(self._path, "w", encoding="utf-8") as fh:
                for it in reversed(self._items):
                    fh.write(json.dumps({
                        "ts": it["ts"], "dir": it["dir"],
                        "ru": it["ru"], "es": it["es"],
                    }, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    @Slot(str, str, str)
    def add(self, direction: str, ru: str, es: str) -> None:
        if not ru:
            return
        ts = time.time()
        item = {
            "ru": ru,
            "es": es or "—",
            "dir": "out" if direction == "out" else "in",
            "ts": ts,
            "time": time.strftime("%H:%M:%S", time.localtime(ts)),
        }
        # новый перевод — первой строкой: актуальное всегда сверху
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._items.insert(0, item)
        self.endInsertRows()
        self._append_file(item)

    @Slot(int)
    def removeAt(self, row: int) -> None:
        if not (0 <= row < len(self._items)):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(row)
        self.endRemoveRows()
        self._rewrite_file()

    @Slot()
    def clear(self) -> None:
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
        self._rewrite_file()

    @Slot(result=int)
    def count(self) -> int:
        return len(self._items)

    @Slot(result=int)
    def retentionDays(self) -> int:
        """Сколько дней храним историю (для подсказки в интерфейсе)."""
        return HISTORY_RETENTION_DAYS

    # ---------- экспорт (ROADMAP 8.8) ----------
    def _export_path(self, ext: str) -> str:
        d = os.path.join(sp.workspace(), "exports")
        os.makedirs(d, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(d, f"history_{stamp}.{ext}")

    @Slot(result=str)
    def exportJson(self) -> str:
        import json
        try:
            path = self._export_path("json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([{k: it[k] for k in ("ts", "dir", "ru", "es")}
                           for it in self._items], fh,
                          ensure_ascii=False, indent=2)
            return path
        except Exception:  # noqa: BLE001
            return ""

    @Slot(result=str)
    def exportTxt(self) -> str:
        try:
            path = self._export_path("txt")
            with open(path, "w", encoding="utf-8") as fh:
                for it in self._items:
                    arrow = "RU -> ES" if it["dir"] == "out" else "ES -> RU"
                    fh.write(f"[{it['time']}] {arrow}: {it['ru']} | {it['es']}\n")
            return path
        except Exception:  # noqa: BLE001
            return ""


# ======================================================================
# Вспомогательное: загрузка записей
# ======================================================================
def _load_records() -> dict[int, str]:
    """Записи образцов: index -> путь WAV."""
    d = sp.output_paths()["samples"]
    out: dict[int, str] = {}
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        low = fn.lower()
        if not low.startswith("take_") or not low.endswith(".wav"):
            continue
        try:
            num = int(low[5:7])
        except Exception:
            continue
        out[num - 1] = os.path.join(d, fn)
    return out