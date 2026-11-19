"""Патч: запись на рабочей частоте устройства + честная диагностика в GUI.

    python tools\\patch_rates.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "app", "studio_core.py")
GUI = os.path.join(ROOT, "app", "voice_studio.py")


def patch_core() -> None:
    with io.open(CORE, encoding="utf-8") as fh:
        src = fh.read()

    old = '''    def start(self, device=None) -> None:
        import sounddevice as sd
        self.buffer = []
        self.device = device
        kwargs = {"device": device} if device is not None else {}
        self._stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                      callback=self._callback, blocksize=1024, **kwargs)
        self._stream.start()
        self.recording = True
'''
    new = '''    def start(self, device=None) -> None:
        import sounddevice as sd
        from audiodev import best_rate
        self.buffer = []
        self.device = device
        # Частота — по устройству: на «чужих» частотах поток отдаёт тишину
        self.sr = best_rate(device, "input", SR)
        kwargs = {"device": device} if device is not None else {}
        self._stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                      callback=self._callback, blocksize=1024, **kwargs)
        self._stream.start()
        self.recording = True
'''
    if old not in src:
        print("core: блок Recorder.start не найден")
        return
    src = src.replace(old, new, 1)

    old2 = '''        self._stream = None
        self.device = None
'''
    new2 = '''        self._stream = None
        self.device = None
        self.sr = SR
'''
    if old2 in src:
        src = src.replace(old2, new2, 1)

    with io.open(CORE, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("core: запись переведена на частоту устройства")


def patch_gui() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()

    old = '''        bridge_text = (
            "Приложение само подмешивает фразы в поток микрофона: микрофон и фразы ->\\n"
            "устройство вывода, которое захватывает Stereo Mix -> микрофон игры.\\n"
            "Твоя обычная речь при этом работает как обычно.\\n\\n"
            "1. Жми «Включить мост» (приложение всё найдёт само).\\n"
            "2. В игре выбери микрофоном «Стерео микшер (Realtek USB Audio)» — один раз.\\n"
            "3. Жми хоткей — фразу услышат все, а ты продолжаешь говорить."
        )
'''
    new = '''        bridge_text = (
            "Мост смешивает твою речь и фразы в один поток и отдаёт его в устройство,\\n"
            "которое ты укажешь. Дальше это устройство выбирается микрофоном в игре.\\n\\n"
            "Что реально доступно на этой машине (проверено):\\n"
            "  • «Стерео микшер (Realtek USB Audio)» ЖИВОЙ (работает на 44100 Гц),\\n"
            "    но игра (RedM/Mumble) его в списке микрофонов НЕ показывает.\\n"
            "  • Игра показывает только реальные микрофоны: Fifine и Razer.\\n"
            "  • Виртуального кабеля в системе нет.\\n\\n"
            "Отсюда три рабочих пути:\\n"
            "  A. Серверный ресурс (вкладка «В игру») — 0 установок, но нужен сервер.\\n"
            "  B. Виртуальный кабель (VoiceMeeter/VB-CABLE) — 1 установка, чистый звук;\\n"
            "     в игре появится «CABLE Output», его выбираешь микрофоном, мост —\\n"
            "     выходом (приложение подставит «CABLE Input» само).\\n"
            "  C. Stereo Mix как микрофон по умолчанию (mmsys.cpl -> Запись -> Стерео\\n"
            "     микшер -> Свойства -> По умолчанию). Сработает, только если в игре\\n"
            "     есть пункт «Системное устройство»."
        )
'''
    if old not in src:
        print("gui: текст моста не найден")
    else:
        src = src.replace(old, new, 1)
        with io.open(GUI, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("gui: блок моста переписан")


if __name__ == "__main__":
    patch_core()
    patch_gui()
