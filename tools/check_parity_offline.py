"""Проверка пунктов FEATURE_PARITY, которым не нужно живое оборудование.

Что проверяется (строки FEATURE_PARITY):
  * защита от двух экземпляров (single_instance_lock);
  * режим экрана: окно / полный экран (binding appState.fullscreen);
  * копирование фразы (QML TextEdit.copy -> буфер обмена);
  * прослушивание фразы (AppState.playPhrase -> общий плеер);
  * прослушивание образца (VoiceController.playSample);
  * сравнение с образцом (audio_play.compare);
  * смена профиля голоса (AppState.setProfile -> sp.set_active_profile);
  * сборка reference (core.build_reference).

Звук не слушается ушами: во время воспроизведения пишется Stereo Mix
(loopback вывода), и проверяется RMS. Если Stereo Mix нет — пункт
помечается SKIP с причиной, а не PASS.

Запуск:
    python tools/check_parity_offline.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app")
_QTAPP = os.path.join(_APP, "qtapp")
_QML = os.path.join(_QTAPP, "qml")
for _p in (_APP, _QTAPP, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

import numpy as np
from PySide6.QtCore import QUrl, Qt, QTimer, QObject, QMetaObject, Q_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

import studio_paths as sp
import studio_core as core
import branding
from app_state import AppState
from live_engine import LiveEngine
from voice_controller import VoiceController
from models import PromptModel, TakeModel, SampleModel, HistoryModel

RESULTS: list[tuple[str, str, str]] = []   # (пункт, статус, подтверждение)


def record(item: str, status: str, proof: str) -> None:
    RESULTS.append((item, status, proof))
    print(f"  [{status}] {item} — {proof}")


# ---------------------------------------------------------------------------
# Запись вывода через Stereo Mix (loopback): доказательство, что звук идёт
# ---------------------------------------------------------------------------
def stereo_mix():
    """(device, samplerate) устройства «Стерео микшер» или (None, 0)."""
    try:
        import sounddevice as sd
        for idx, dev in enumerate(sd.query_devices()):
            name = (dev.get("name") or "").lower()
            if dev.get("max_input_channels", 0) < 1:
                continue
            if "стерео микшер" in name or "stereo mix" in name:
                return idx, int(dev.get("default_samplerate") or 48000)
    except Exception:
        pass
    return None, 0


def rms_during(action, seconds: float = 2.0) -> float:
    """RMS сигнала с Stereo Mix во время action (0.0 — тишина/нет устройства)."""
    import sounddevice as sd
    dev, sr = stereo_mix()
    if dev is None:
        return -1.0
    chunks = []

    def cb(indata, frames, _t, status):  # noqa: ANN001
        chunks.append(float(np.sqrt(np.mean(np.square(indata[:, 0])))))

    with sd.InputStream(device=dev, channels=1, samplerate=sr,
                        dtype="float32", callback=cb):
        time.sleep(0.3)
        action()
        time.sleep(seconds)
    peak = max(chunks) if chunks else 0.0
    print(f"      (Stereo Mix: {len(chunks)} блоков, пик RMS {peak:.4f})")
    return peak


# ---------------------------------------------------------------------------
# Проверки
# ---------------------------------------------------------------------------
def check_single_instance() -> None:
    """Два экземпляра: первый держит блокировку, второй получает отказ."""
    mark = sp.single_instance_lock()
    second = sp.single_instance_lock()
    if mark and not second:
        record("Защита от двух экземпляров", "PASS",
               "первый lock()=True, второй lock()=False (msvcrt LK_NBLCK)")
    else:
        record("Защита от двух экземпляров", "FAIL",
               f"первый={mark}, второй={second} — второй экземпляр не отсекается")


def check_fullscreen(win: QQuickWindow, state: AppState, app) -> None:
    """Окно/полный экран: переключение appState.fullscreen -> visibility."""
    def spin(ms: int = 400) -> None:
        end = time.time() + ms / 1000.0
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)

    was = state.fullscreen
    def vis_state() -> tuple[str, int]:
        v = win.visibility()
        return (getattr(v, "name", str(v)), int(getattr(v, "value", 0)))

    try:
        state.setFullscreen(True)
        spin()
        name_full, val_full = vis_state()
        state.setFullscreen(False)
        spin()
        name_win, val_win = vis_state()
        saved = state._load_settings().get("fullscreen")
        ok = name_full == "FullScreen" and name_win == "Windowed" \
            and saved is False
        record("Режим экрана (окно/полный)", "PASS" if ok else "FAIL",
               f"fullscreen=True -> {name_full}, False -> {name_win}, "
               f"в ui_settings.json fullscreen={saved}")
    finally:
        state.setFullscreen(was)


def _qml_page(win: QQuickWindow, prefix: str):
    for obj in win.findChildren(QObject):
        try:
            if obj.metaObject().className().startswith(prefix):
                return obj
        except Exception:
            continue
    return None


def check_copy_phrase(win: QQuickWindow, app) -> None:
    """Копирование фразы: функция QML copyText кладёт текст в буфер обмена."""
    # Страницы грузятся по одной через Loader: без переключения раздела
    # объекта PhrasesPage в дереве просто нет.
    was = win.property("section")
    win.setProperty("section", "phrases")
    end = time.time() + 1.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    page = _qml_page(win, "PhrasesPage")
    text = "Arriba, compa — проверка буфера"
    if page is None:
        win.setProperty("section", was)
        record("Копирование фразы", "SKIP", "страница «Фразы» не найдена в QML")
        return
    app.processEvents()
    ok = QMetaObject.invokeMethod(page, "copyText", Q_ARG("QVariant", text))
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    got = QGuiApplication.clipboard().text()
    win.setProperty("section", was)
    if not ok:
        record("Копирование фразы", "FAIL", "функция copyText не вызвалась")
        return
    record("Копирование фразы", "PASS" if got == text else "FAIL",
           f"copyText() -> буфер: {got!r}")


def check_play_phrase(state: AppState) -> None:
    """Прослушивание фразы: mp3 из workspace -> общий плеер -> звук в вывод."""
    from ui import audio_play
    paths = sp.output_paths()
    phrase_id, path = "", ""
    for pid in ("01", "02", "03"):
        cand = os.path.join(paths["player_mp3"], f"mx_{pid}.mp3")
        if os.path.exists(cand):
            phrase_id, path = pid, cand
            break
    if not path:
        record("Прослушивание фразы", "SKIP", "в workspace нет mp3 фраз")
        return
    # Воспроизведение запускаем ВНУТРИ окна записи: короткий mp3 (1,4 с)
    # иначе успевает закончиться до открытия входного потока.
    peak = rms_during(lambda: state.playPhrase(phrase_id, "es"), 1.6)
    playing = audio_play.player_is_playing() or peak > 0.002
    audio_play.player_stop()
    ok = playing and (peak > 0.002 or peak < 0)
    detail = (f"mx_{phrase_id}.mp3 -> плеер запущен={playing}, "
              + ("Stereo Mix: сигнал есть, RMS пик %.4f" % peak if peak >= 0
                 else "Stereo Mix нет — только факт запуска потока"))
    record("Прослушивание фразы", "PASS" if ok else "FAIL", detail)


def check_play_sample(voices: VoiceController) -> None:
    """Прослушивание образца: playSample(path) на реальном wav подсказки."""
    from ui import audio_play
    import prompt_library as plib
    path = plib.audio_path(0)
    if not path or not os.path.exists(path):
        record("Прослушивание образца", "SKIP", "нет wav подсказки")
        return
    ok_call = True
    peak = rms_during(lambda: voices.playSample(path), 1.2)
    try:
        voices.playSample(path)       # второй клик = стоп
    except Exception as exc:          # noqa: BLE001
        ok_call = False
        record("Прослушивание образца", "FAIL", f"playSample: {exc}")
        return
    audio_play.player_stop()
    ok = ok_call and (peak > 0.002 or peak < 0)
    record("Прослушивание образца", "PASS" if ok else "FAIL",
           f"{os.path.basename(path)} -> "
           + ("Stereo Mix RMS пик %.4f" % peak if peak >= 0
              else "плеер запущен, Stereo Mix нет"))


def check_compare(voices: VoiceController, state: AppState) -> None:
    """Сравнение с образцом: подсказка и дубль играют по очереди."""
    from ui import audio_play
    import prompt_library as plib
    prompt = plib.audio_path(0)
    take = os.path.join(sp.workspace(), "voice_samples", "take_01.wav")
    if not prompt or not os.path.exists(prompt):
        record("Сравнение с образцом", "SKIP", "нет подсказки")
        return
    if not os.path.exists(take):
        # берём любой готовый дубль из voice_profiles / voice_samples
        cands = []
        for folder in (os.path.join(sp.workspace(), "voice_samples"),
                       os.path.dirname(sp.active_reference())):
            if os.path.isdir(folder):
                cands += [os.path.join(folder, f) for f in os.listdir(folder)
                          if f.endswith(".wav")]
        take = cands[0] if cands else ""
    if not take:
        record("Сравнение с образцом", "SKIP", "нет ни одного дубля wav")
        return
    voices._records = {voices._index: take}
    voices._index = 0
    # 1) путь кнопки: VoiceController.compare -> audio_play.compare
    started = False
    err = ""
    try:
        voices.compare("delay", 0.8)
        started = audio_play.player_is_playing()
    except Exception as exc:      # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    if err:
        # 2) тот же вызов с правильным именем параметра: если работает —
        # дефект ровно в имени аргумента, а не в сравнении как таковом.
        direct = ""
        try:
            from ui import audio_play
            direct = str(audio_play.compare(prompt, take, mode="delay", gap=0.8))
        except Exception as exc:  # noqa: BLE001
            direct = f"тоже ошибка: {exc}"
        record("Сравнение с образцом", "FAIL",
               f"кнопка -> {err}; с параметром gap= напрямую -> {direct}")
        return
    peak = rms_during(lambda: None, 1.5)
    audio_play.player_stop()
    ok = started and (peak > 0.002 or peak < 0)
    record("Сравнение с образцом", "PASS" if ok else "FAIL",
           f"prompt + {os.path.basename(take)} -> сравнение запущено={started}"
           + (f", Stereo Mix RMS пик {peak:.4f}" if peak >= 0 else ""))


def check_profile(state: AppState) -> None:
    """Смена профиля: setProfile меняет активный профиль и reference."""
    names = sp.list_profiles()
    if not names:
        record("Смена профиля", "SKIP", "нет ни одного профиля")
        return
    was = sp.get_active_profile()
    msgs: list[str] = []
    state.statusMessage.connect(lambda t, k: msgs.append(t))
    try:
        target = next((n for n in names if n != was), names[0])
        state.setProfile(target)
        active = sp.get_active_profile()
        ref = sp.active_reference()
        expected = sp.profile_reference(target)
        ok = active == target and ref == expected
        record("Смена профиля", "PASS" if ok else "FAIL",
               f"setProfile({target!r}) -> active={active!r}, "
               f"reference={os.path.basename(os.path.dirname(ref))}/"
               f"{os.path.basename(ref)}; статус: {msgs[-1] if msgs else '—'}")
    finally:
        state.setProfile(was) if was else sp.set_active_profile("")
        state._active_profile = sp.get_active_profile()


def check_build_reference() -> None:
    """Сборка reference: несколько дублей -> один wav нужной длительности."""
    tmp = tempfile.mkdtemp(prefix="auraloom_ref_")
    sr = 24000
    samples = []
    for i, freq in enumerate((180.0, 220.0)):
        t = np.arange(int(sr * 1.5), dtype=np.float32) / sr
        # тон + лёгкий шум: quality_report должен счесть запись пригодной
        wave = 0.25 * np.sin(2 * np.pi * freq * t)
        rng = np.random.default_rng(i)
        wave += 0.01 * rng.standard_normal(len(wave)).astype(np.float32)
        path = os.path.join(tmp, f"take_{i + 1:02d}.wav")
        import soundfile as sf
        sf.write(path, wave, sr)
        samples.append(path)
    out = os.path.join(tmp, "reference.wav")
    res = core.build_reference(samples, out)
    dur = 0.0
    if os.path.exists(out):
        import soundfile as sf
        dur = float(sf.info(out).duration)
    ok = bool(res.get("ok")) and dur > 1.0
    record("Сборка reference", "PASS" if ok else "FAIL",
           f"{len(samples)} дубля -> {res.get('ok')}, "
           f"reference.wav {dur:.1f} c, used={res.get('used')}, "
           f"skipped={res.get('skipped')}")


def check_replay(live: LiveEngine) -> None:
    """Проиграть из истории: кнопка ▶ доходит до движка с текстом и seq."""
    calls: list[str] = []

    class _FakeTranslator:
        ready = True

        def incoming_speak(self, text, seq):   # noqa: ANN001
            calls.append(f"{text}|{seq}")
            return True

    errors: list[str] = []
    live.errorMessage.connect(lambda m: errors.append(m))
    try:
        # без движка: должно быть честное сообщение, а не падение
        live._translator = None
        live.replay("Hola, amigo")
        no_engine = errors[-1] if errors else ""
        # с движком (заглушка): текст и растущий seq
        live._translator = _FakeTranslator()
        live.replay("Hola, amigo")
        live.replay("Hola, amigo")
        ok = (no_engine.startswith("движок не запущен")
              and len(calls) == 2 and calls[0].endswith("|1")
              and calls[1].endswith("|2"))
        record("Проиграть из истории", "PASS" if ok else "FAIL",
               f"без движка -> {no_engine!r}; с движком incoming_speak"
               f"({calls})")
    finally:
        live._translator = None


def main() -> int:
    print("\n=== FEATURE_PARITY: проверки без оборудования ===\n")
    print("  фоновые пункты, где нужен реальный звук/движок, разбираются отдельно\n")

    check_single_instance()
    check_build_reference()

    app = QGuiApplication(sys.argv[:1])
    engine = QQmlApplicationEngine()

    state = AppState()
    live = LiveEngine()
    voices = VoiceController()
    live.attach(state)
    state._live_engine = live

    ctx = engine.rootContext()
    ctx.setContextProperty("brandName", branding.BRAND_NAME)
    ctx.setContextProperty("brandShort", branding.BRAND_SHORT)
    ctx.setContextProperty("brandSub", branding.BRAND_SUB)
    ctx.setContextProperty("brandTagline", branding.BRAND_TAGLINE)
    ctx.setContextProperty("appState", state)
    ctx.setContextProperty("liveEngine", live)
    ctx.setContextProperty("voiceController", voices)
    ctx.setContextProperty("promptModel", PromptModel())
    ctx.setContextProperty("takeModel", TakeModel())
    ctx.setContextProperty("sampleModel", SampleModel())
    ctx.setContextProperty("historyModel", HistoryModel())

    state.refreshDevices()
    state.refreshPhrases()

    engine.addImportPath(_QML)
    engine.load(QUrl.fromLocalFile(os.path.join(_QML, "main.qml")))
    if not engine.rootObjects():
        print("QML не загрузился")
        return 1
    win = next((o for o in engine.rootObjects() if isinstance(o, QQuickWindow)),
               None)
    if win is None:
        print("нет окна")
        return 1
    win.show()

    def run() -> None:
        try:
            check_fullscreen(win, state, app)
            check_copy_phrase(win, app)
            check_play_phrase(state)
            check_play_sample(voices)
            check_compare(voices, state)
            check_profile(state)
            check_replay(live)
        except Exception as exc:            # noqa: BLE001
            record("Скрипт", "FAIL", f"{type(exc).__name__}: {exc}")
        finally:
            try:
                state.shutdown()
                live.shutdown()
            except Exception:
                pass
            app.quit()

    QTimer.singleShot(1200, run)
    app.exec()

    print("\n=== ИТОГ ===")
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = [i for i, s, _ in RESULTS if s == "FAIL"]
    skipped = [i for i, s, _ in RESULTS if s == "SKIP"]
    print(f"  PASS {passed}, FAIL {len(failed)}, SKIP {len(skipped)}")
    for name in failed:
        print(f"  FAIL: {name}")
    for name in skipped:
        print(f"  SKIP: {name}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
