"""Глобальные горячие клавиши (Windows) и вывод звука в выбранное устройство.

Нужно, чтобы звуковая панель работала, когда в фокусе игра, а не приложение.
Регистрируем WM_HOTKEY на NULL — сообщение приходит в очередь сообщений
отдельного потока, откуда мы и читаем.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_HK_WAKE = 0x8000 + 1  # своё сообщение: «просни, есть запрос на регистрацию»

VK_CODES = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
    # клавиши-модификаторы — их можно назначить как одиночную клавишу
    "alt": 0x12, "ctrl": 0x11, "shift": 0x10, "win": 0x5B,
    "capslock": 0x14,
}

# Буквы и прочие клавиши — для назначения пользователем
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    VK_CODES[_ch] = 0x41 + _i
VK_CODES.update({
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "backspace": 0x08,
    "escape": 0x1B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "pause": 0x13, "scroll_lock": 0x91,
    "printscreen": 0x2C,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F, "f17": 0x80,
    "f18": 0x81, "f19": 0x82, "f20": 0x83, "f21": 0x84, "f22": 0x85,
    "f23": 0x86, "f24": 0x87,
})

# Названия клавиш Tk -> наши коды
KEYSYM_TO_KEY = {
    "space": "space", "tab": "tab", "return": "enter", "enter": "enter",
    "backspace": "backspace", "insert": "insert", "delete": "delete",
    "home": "home", "end": "end", "prior": "pageup", "next": "pagedown",
    "page_up": "pageup", "page_down": "pagedown",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "pause": "pause", "scroll_lock": "scroll_lock", "escape": "escape",
    "grave": "`", "minus": "-", "equal": "=", "bracketleft": "[",
    "bracketright": "]", "backslash": "\\", "semicolon": ";", "apostrophe": "'",
    "comma": ",", "period": ".", "slash": "/",
    # модификаторы: чтобы их можно было назначить (например, одиночный Alt)
    "alt_l": "alt", "alt_r": "alt",
    "control_l": "ctrl", "control_r": "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "super_l": "win", "super_r": "win",
    "meta_l": "win", "meta_r": "win",
    "caps_lock": "capslock",
}
for _i in range(1, 13):
    KEYSYM_TO_KEY[f"f{_i}"] = f"f{_i}"
for _i in range(10):
    KEYSYM_TO_KEY[f"kp_{_i}"] = f"numpad{_i}"


def key_from_keysym(keysym: str) -> str:
    """Клавиша Tk -> наш код ('f5', 'space', 'a'). '' если не поддерживается."""
    if not keysym:
        return ""
    ks = keysym.lower()
    if ks in KEYSYM_TO_KEY:
        return KEYSYM_TO_KEY[ks]
    if len(ks) == 1 and ks in VK_CODES:
        return ks
    return ""


# Модификаторы комбинации -> флаги Windows
MOD_BY_NAME = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT, "shift": MOD_SHIFT,
    "win": 0x0008, "super": 0x0008,
}


def parse_combo(combo: str) -> tuple[str, int]:
    """'ctrl+alt+g' -> ('g', mods). ('', 0) если разобрать нельзя.

    Поддерживается и одиночная клавиша ('g' -> без модификаторов),
    и одиночный модификатор ('alt' -> только Alt).
    """
    if not combo:
        return "", 0
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        return "", 0
    key = parts[-1]
    mods = 0
    for name in parts[:-1]:
        mods |= MOD_BY_NAME.get(name, 0)
    if key not in VK_CODES:
        return "", 0
    return key, mods


def combo_from_event(keysym: str, state: int) -> str:
    """Клавиша Tk + состояние модификаторов -> комбинация ('ctrl+alt+g').

    state — битовая маска Tk: Shift=1, Lock=2, Control=4, Mod1=8, Mod2=16,
    Mod3=32, Mod4=64. На Windows Alt попадает в Mod1 (иногда в Mod2).
    """
    key = key_from_keysym(keysym)
    if not key:
        return ""
    mods = []
    if state & 0x0001:
        mods.append("shift")
    if state & 0x0004:
        mods.append("ctrl")
    if state & 0x0008:      # Mod1 — обычно Alt
        mods.append("alt")
    if state & 0x0010:      # Mod2 — иногда Alt
        if "alt" not in mods:
            mods.append("alt")
    if state & 0x0040:      # Mod4 — иногда Win
        mods.append("win")
    # нажат сам модификатор — он и есть назначаемая клавиша
    if key in ("alt", "ctrl", "shift", "win"):
        mods = [m for m in mods if m != key]
    return "+".join(mods + [key])


def vk_of(combo: str) -> int:
    """Числовой код клавиши по комбинации ('ctrl+alt+t' -> VK_T).

    Нужно, чтобы следить за ОТПУСКАНИЕМ клавиши: Windows шлёт WM_HOTKEY
    только на нажатии, а «отпустил» мы определяем по GetAsyncKeyState.
    """
    if not combo:
        return 0
    if "+" in combo:
        name, _mods = parse_combo(combo)
    else:
        name = combo
    return VK_CODES.get(name.lower(), 0) if name else 0


def pretty_combo(combo: str) -> str:
    """'ctrl+alt+g' -> 'Ctrl+Alt+G'."""
    if not combo:
        return "—"
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win",
             "space": "Пробел", "enter": "Enter", "tab": "Tab",
             "escape": "Esc", "backspace": "Backspace"}
    parts = []
    for p in combo.split("+"):
        low = p.lower()
        parts.append(names.get(low, low.upper() if len(low) == 1 else low))
    return "+".join(parts)


class GlobalHotkeys:
    """Регистрация глобальных хоткеев в отдельном потоке.

    ВАЖНО: RegisterHotKey(NULL, ...) привязывает WM_HOTKEY к потоку, который
    её вызвал. Если регистрировать из главного потока GUI, а читать сообщения
    в отдельном — сообщение уйдёт в очередь главного потока и потеряется.
    Поэтому регистрация выполняется ТОЖЕ в потоке-читателе: запросы
    кладутся в очередь, поток их применяет и возвращает результат.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._ids: dict[int, str] = {}
        self._callback = None
        self._next_id = 0xB000
        self._lock = threading.Lock()
        self._running = False
        # очередь запросов к потоку-читателю: (вид, данные, событие, результат)
        # вид: 'reg' (зарегистрировать) или 'unreg' (снять)
        self._pending: list[tuple[str, tuple, threading.Event, list]] = []
        self._pending_lock = threading.Lock()
        self._ready = threading.Event()
        # код последней ошибки RegisterHotKey (1409 = клавиша занята)
        self._last_error = 0

    def set_callback(self, fn) -> None:
        self._callback = fn

    def register(self, key: str, action: str,
                 mods: int = MOD_CONTROL | MOD_ALT) -> bool:
        """Зарегистрировать хоткей.

        key — либо комбинация ('ctrl+alt+g', 'g', 'alt'), либо просто код
        клавиши ('1', 'f5'). Для комбинации модификаторы берутся из неё;
        mods используется только для одиночных кодов.
        """
        vk, use_mods = self._key_and_mods(key, mods)
        if not vk:
            return False
        # Поток-читатель должен быть запущен: WM_HOTKEY приходит именно в
        # его очередь. Если он не запущен — запускаем, иначе регистрация
        # привяжет хоткей к потоку GUI, и сообщение потеряется.
        self.start()
        done = threading.Event()
        result: list[bool] = []
        with self._pending_lock:
            self._pending.append(("reg", (key, action, use_mods), done, result))
        # будим поток-читатель: GetMessage блокирует, а PeekMessage в этой
        # среде сообщения из очереди потока не видит
        self._wake_reader()
        done.wait(timeout=3.0)
        return bool(result and result[0])

    @staticmethod
    def _key_and_mods(key: str, mods: int) -> tuple[int, int]:
        """'ctrl+alt+g' -> (VK_G, mods). (0, 0) если разобрать нельзя.

        ВАЖНО: возвращается ЧИСЛОВЫЙ код клавиши. Раньше для комбинаций
        возвращалось ИМЯ ('l'), и RegisterHotKey получал строку вместо кода —
        комбинации не работали никогда.
        """
        if "+" in key:
            name, combo_mods = parse_combo(key)
            if not name:
                return 0, 0
            vk = VK_CODES.get(name.lower())
            if not vk:
                return 0, 0
            return vk, (combo_mods or mods)
        vk = VK_CODES.get(key.lower())
        return (vk, mods) if vk else (0, 0)

    def _register_now(self, vk: int, action: str, mods: int) -> bool:
        with self._lock:
            hotkey_id = self._next_id
            self._next_id += 1
        if not user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
            # 1409 = ERROR_HOTKEY_ALREADY_REGISTERED: клавишу держит
            # другая программа (или мы сами, если регистрируем дважды)
            try:
                err = ctypes.get_last_error()
            except Exception:
                err = 0
            self._last_error = err
            print(f"RegisterHotKey не сработал: vk={vk} mods={mods} err={err}")
            return False
        with self._lock:
            self._ids[hotkey_id] = action
        return True

    def register_many(self, items: list[tuple[str, str, int]]) -> list[str]:
        """Зарегистрировать несколько хоткеев. items = [(key, action, mods)].

        Возвращает список действий, которые зарегистрировать НЕ удалось
        (например, клавиша уже занята другой программой).
        """
        failed = []
        for key, action, mods in items:
            if not key:
                continue
            if not self.register(key, action, mods):
                failed.append(action)
        return failed

    def unregister_all(self) -> None:
        self._unregister(lambda action: True)

    def unregister_prefix(self, prefix: str) -> None:
        """Снять только хоткеи с данным префиксом (остальные оставить).

        Нужно, чтобы вкладки «Микрофон» (фразы) и «Живой перевод» не мешали
        друг другу: каждая снимает только свои.
        """
        self._unregister(lambda action: action.startswith(prefix))

    def _unregister(self, match) -> None:
        """Снять хоткеи, подходящие под match(action).

        ВАЖНО: UnregisterHotKey(NULL, ...) работает ТОЛЬКО из потока, который
        регистрировал хоткей. Поэтому снятие тоже идёт через очередь
        потока-читателя — иначе хоткей оставался занятым, и повторное
        включение всегда падало с «клавиша занята».
        """
        if not self._thread or not self._thread.is_alive():
            with self._lock:
                self._ids.clear()
            return
        done = threading.Event()
        result: list[bool] = []
        with self._pending_lock:
            self._pending.append(("unreg", (match,), done, result))
        self._wake_reader()
        done.wait(timeout=3.0)

    def registered(self, prefix: str = "") -> list[str]:
        """Список зарегистрированных действий (с префиксом, если указан)."""
        with self._lock:
            return [a for a in self._ids.values() if a.startswith(prefix)]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        # ждём, пока поток поднимется — иначе register() пойдёт мимо него
        self._ready.wait(timeout=2.0)

    def _wake_reader(self) -> bool:
        """Разбудить поток-читатель (чтобы он применил очередь).

        PostThreadMessageW может не сработать, если у потока ещё нет очереди
        сообщений. Поэтому повторяем попытку несколько раз.
        """
        for _ in range(20):
            if user32.PostThreadMessageW(self._thread.ident, WM_HK_WAKE, 0, 0):
                return True
            time.sleep(0.02)
        return False

    def _apply_pending(self) -> None:
        """Применить накопленные запросы (из потока-читателя)."""
        with self._pending_lock:
            pending = self._pending
            self._pending = []
        for kind, data, done, result in pending:
            try:
                if kind == "reg":
                    key, action, mods = data
                    vk, use_mods = self._key_and_mods(key, mods)
                    ok = self._register_now(vk, action, use_mods) if vk else False
                else:
                    (match,) = data
                    ok = self._unregister_now(match)
            except Exception as exc:  # noqa: BLE001
                # Ошибка здесь не должна убивать поток-читатель: иначе
                # следующие запросы на регистрацию будут ждать таймаут.
                print(f"ошибка в очереди хоткеев ({kind}): {type(exc).__name__}: {exc}")
                ok = False
            result.append(ok)
            done.set()

    def _unregister_now(self, match) -> bool:
        """Снять хоткеи (только из потока-читателя — иначе не сработает)."""
        with self._lock:
            targets = [(hid, act) for hid, act in self._ids.items() if match(act)]
            for hotkey_id, _action in targets:
                user32.UnregisterHotKey(None, hotkey_id)
                self._ids.pop(hotkey_id, None)
        return True

    def _loop(self) -> None:
        """Читаем сообщения потока.

        GetMessage блокирует — и это единственный способ увидеть WM_HOTKEY
        в очереди потока (PeekMessage здесь их не видит). Чтобы поток
        просыпался на запрос регистрации, шлём ему WM_HK_WAKE.
        """
        # ВАЖНО: очередь сообщений потока создаётся ПЕРВЫМ вызовом GetMessage.
        # Раньше _ready ставился раньше, и PostThreadMessageW уходил в
        # несуществующую очередь — первая регистрация терялась (хоткей
        # «не работал», а код ошибки был 0: RegisterHotKey даже не вызывался).
        # Поэтому сначала создаём очередь, потом сообщаем «я готов».
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # PM_NOREMOVE
        self._ready.set()
        while self._running:
            msg = wt.MSG()
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got in (0, -1):
                break
            try:
                if msg.message == WM_HK_WAKE:
                    self._apply_pending()
                    continue
                if msg.message == WM_HOTKEY:
                    with self._lock:
                        action = self._ids.get(msg.wParam)
                    if action and self._callback:
                        try:
                            self._callback(action)
                        except Exception:
                            pass
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as exc:  # noqa: BLE001
                # Поток-читатель не должен умирать: иначе все хоткеи
                # перестанут работать, и регистрация будет висеть до таймаута.
                print(f"цикл хоткеев: {type(exc).__name__}: {exc}")
        self._apply_pending()


# --------------------------------------------------------------------------
# Аудиоустройства
# --------------------------------------------------------------------------
def list_devices() -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(вводы, выводы) как список (индекс, имя)."""
    import sounddevice as sd
    inputs, outputs = [], []
    for i, d in enumerate(sd.query_devices()):
        name = d["name"]
        if d["max_input_channels"] > 0:
            inputs.append((i, name))
        if d["max_output_channels"] > 0:
            outputs.append((i, name))
    return inputs, outputs


def default_devices() -> tuple[int | None, int | None]:
    """(микрофон по умолчанию, вывод по умолчанию)."""
    import sounddevice as sd
    try:
        return sd.default.device[0], sd.default.device[1]
    except Exception:
        return None, None


def is_virtual_cable(name: str) -> bool:
    """Похоже на виртуальный кабель (VoiceMeeter / VB-CABLE)?"""
    low = name.lower()
    return any(k in low for k in ("cable", "voicemeeter", "virtual", "vb-audio",
                                  "vb-cable", "loopback"))


def is_stereo_mix(name: str) -> bool:
    """Stereo Mix («Стерео микшер», «что слышно») — встроен в Windows.

    Позволяет обойтись БЕЗ виртуального кабеля: приложение играет фразу в
    устройство вывода, Stereo Mix захватывает этот звук, а игра берёт
    микрофоном сам Stereo Mix.
    """
    low = name.lower()
    return any(k in low for k in ("stereo mix", "стерео микшер", "stereomix",
                                  "what u hear", "wave out"))


def find_stereo_mix(inputs: list[tuple[int, str]]) -> tuple[int | None, str]:
    """Найти устройство Stereo Mix среди входов."""
    for i, name in inputs:
        if is_stereo_mix(name):
            return i, name
    return None, ""


def find_render_for_capture(inputs: list[tuple[int, str]],
                            outputs: list[tuple[int, str]]) -> tuple[int | None, str]:
    """Устройство вывода, которое захватывает найденный Stereo Mix.

    У Stereo Mix имя родительского устройства стоит в скобках:
    «Стерео микшер (Realtek USB Audio)» -> ищем выход с «Realtek USB Audio».
    Если скобок нет — отбрасываем слова «микшер/mixer».
    """
    _, mix_name = find_stereo_mix(inputs)
    if not mix_name:
        return None, ""

    core = ""
    if "(" in mix_name and ")" in mix_name:
        core = mix_name[mix_name.find("(") + 1: mix_name.find(")")].strip()
    if not core:
        core = mix_name
        for cut in ("стерео микшер", "stereo mix", "микшер", "mixer"):
            core = core.replace(cut, "")
        core = core.replace("(", "").replace(")", "").strip()
    if not core:
        return None, ""

    matches = [(i, n) for i, n in outputs if core.lower() in n.lower()]
    if not matches:
        return None, ""

    try:
        import sounddevice as sd
        default_out = sd.default.device[1]
    except Exception:
        default_out = None

    def rank(item: tuple[int, str]) -> tuple[int, int, int]:
        i, n = item
        low = n.lower()
        # 0 — наушники/динамики (то, что реально слышно), 1 — прочее
        is_speakers = any(k in low for k in ("наушники", "динамики", "headphone",
                                             "speaker", "динамик"))
        # цифровые выходы (S/PDIF и т.п.) — хуже: туда уходит не то, что слышно
        is_digital = any(k in low for k in ("digital", "spdif", "интерфейс", "output"))
        return (0 if is_speakers else (2 if is_digital else 1),
                0 if i == default_out else 1,
                i)

    matches.sort(key=rank)
    return matches[0]


def play_file(path: str, device: int | None = None, volume: float = 1.0) -> float:
    """Проиграть файл на выбранном устройстве вывода. Возвращает длительность."""
    import soundfile as sf
    import sounddevice as sd
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if volume != 1.0:
        data = data * volume
    kwargs = {"device": device} if device is not None else {}
    sd.play(data, samplerate=sr, **kwargs)
    return len(data) / sr


def measure_input(device: int | None = None, seconds: float = 3.0) -> dict:
    """Измерить уровень на входе: пик, RMS и «есть ли сигнал»."""
    import sounddevice as sd
    import numpy as np
    kwargs = {"device": device} if device is not None else {}
    rec = sd.rec(int(seconds * 44100), samplerate=44100, channels=1,
                  dtype="float32", **kwargs)
    sd.wait()
    audio = np.asarray(rec, dtype="float32").squeeze()
    if audio.size == 0:
        return {"peak": 0.0, "rms": 0.0, "verdict": "микрофон молчит"}
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
    verdict = ("сигнал идёт — маршрут работает" if rms > 0.004
               else "тишина: сигнал не доходит до микрофона")
    return {"peak": peak, "rms": rms, "verdict": verdict}
