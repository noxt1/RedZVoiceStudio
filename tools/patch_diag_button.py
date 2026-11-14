"""Патч: кнопка «Диагностика» на вкладке «Микрофон».

Показывает по каждому устройству: открывается ли, на какой частоте и есть ли
loopback (перехват системного звука), который вообще может пригодиться.

    python tools\\patch_diag_button.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.path.join(ROOT, "app", "voice_studio.py")

OLD = '''        self._btn(btns, "⬇ Установить VoiceMeeter", self._install_cable).pack(side="left")
'''

NEW = '''        self._btn(btns, "⬇ Установить VoiceMeeter", self._install_cable).pack(side="left")
        self._btn(btns, "🔍 Диагностика устройств", self._diag_devices).pack(
            side="left", padx=(8, 0))
'''

OLD2 = '''    def _install_cable(self) -> None:'''
NEW2 = '''    def _diag_devices(self) -> None:
        """Показать реальное состояние аудиоустройств."""
        import audiodev
        import sounddevice as sd

        self.mic_status.config(text="Проверяю устройства...")
        self.root.update()
        lines = []

        try:
            devices = sd.query_devices()
        except Exception as exc:  # noqa: BLE001
            self.mic_status.config(text=f"Устройства: {exc}")
            return

        for kind, label in (("input", "ВХОД"), ("output", "ВЫХОД")):
            lines.append(f"--- {label} ---")
            seen = set()
            for i, d in enumerate(devices):
                if kind == "input" and d["max_input_channels"] <= 0:
                    continue
                if kind == "output" and d["max_output_channels"] <= 0:
                    continue
                key = d["name"].split("(")[0].strip()
                if key in seen:
                    continue
                seen.add(key)
                rates = audiodev.working_rates(i, kind)
                if rates:
                    lines.append(f"  {d['name'][:38]:<40} ок: {rates[0]} Гц")
                else:
                    lines.append(f"  {d['name'][:38]:<40} НЕ ОТКРЫВАЕТСЯ")

        loop = [(i, d["name"]) for i, d in enumerate(devices)
                if d["max_input_channels"] > 0
                and any(k in d["name"].lower() for k in
                        ("стерео микшер", "stereo mix", "loopback"))]
        lines.append("")
        if loop:
            lines.append("Перехват системного звука (loopback):")
            for i, n in loop:
                rates = audiodev.working_rates(i, "input")
                lines.append(f"  {n[:44]:<46} {rates[0] if rates else 'не работает'} Гц")
            lines.append("Но RedM/Mumble обычно НЕ показывает его в списке микрофонов.")
        else:
            lines.append("Loopback-устройств в системе нет — для маршрута в микрофон "
                         "нужен виртуальный кабель.")

        text = "\\n".join(lines)
        panel = getattr(self, "task_panel", None)
        if panel is not None:
            panel.begin("Диагностика аудиоустройств", ["Проверка входов", "Проверка выходов",
                                                       "Поиск loopback"], 3)
            panel.step(0, "done")
            panel.step(1, "done")
            panel.step(2, "done", "итог в журнале")
            for line in lines:
                panel.log("dim" if line.startswith("---") else "", line)
            panel.finish(True)
        self.mic_status.config(text="Диагностика — в журнале")

    def _install_cable(self) -> None:'''


def main() -> None:
    with io.open(GUI, encoding="utf-8") as fh:
        src = fh.read()
    applied = []
    if OLD in src:
        src = src.replace(OLD, NEW, 1)
        applied.append("кнопка")
    else:
        print("  ! кнопка не найдена")
    if OLD2 in src:
        src = src.replace(OLD2, NEW2, 1)
        applied.append("метод")
    else:
        print("  ! метод не найден")
    with io.open(GUI, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Применено:", ", ".join(applied) if applied else "ничего")


if __name__ == "__main__":
    main()
