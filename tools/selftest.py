"""Самопроверка установки: проверяет всё, что нужно для работы в игре.

    python tools\\selftest.py           # быстро (без оценки схожести)
    python tools\\selftest.py --full    # плюс замер схожести голоса (медленно)

Печатает чек-лист с вердиктом по каждому пункту.
"""

from __future__ import annotations

import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

OK = "OK  "
FAIL = "!!  "
WARN = "?   "


def check(name: str, ok: bool, detail: str = "", warn: bool = False) -> bool:
    mark = WARN if warn else (OK if ok else FAIL)
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> None:
    import studio_core as core
    import studio_paths as sp

    print("\n=== 1. Окружение ===")
    sp.seed_workspace()
    ws = sp.workspace()
    check("рабочая папка", os.path.isdir(ws), ws)
    engine = sp.engine_python()
    check("движок XTTS", engine is not None, engine or "не найден -> tools\\setup_env.ps1")
    check("голоса Piper es-MX", len(glob.glob(os.path.join(ws, "voices", "*.onnx"))) == 2)

    print("\n=== 2. Озвучка ===")
    mp3 = sorted(glob.glob(os.path.join(ws, "out", "mp3", "mx_*.mp3")))
    check("фраз озвучено", len(mp3) >= 31, f"{len(mp3)} шт")
    ref = os.path.join(ws, "reference.wav")
    check("образец голоса", os.path.exists(ref),
          f"{os.path.getsize(ref) // 1024} KB" if os.path.exists(ref) else "нет")
    samples = glob.glob(os.path.join(ws, "voice_samples", "take_*.wav"))
    check("записи подсказок", len(samples) >= 5, f"{len(samples)} шт")

    print("\n=== 3. Устройства и маршрут ===")
    import hotkeys as hk
    try:
        inputs, outputs = hk.list_devices()
    except Exception as exc:  # noqa: BLE001
        print(f"  {FAIL} аудиоустройства: {exc}")
        return
    mix_i, mix_n = hk.find_stereo_mix(inputs)
    check("Stereo Mix (вход игры)", mix_i is not None, mix_n or "не найден")
    r_i, r_n = hk.find_render_for_capture(inputs, outputs)
    check("устройство вывода под Stereo Mix", r_i is not None, r_n or "не найдено")
    mic_i, mic_n = core.pick_input_device()
    check("микрофон", mic_i is not None, mic_n or "не найден")

    print("\n=== 4. Мост микрофон -> выход ===")
    if mix_i is None or r_i is None:
        print(f"  {FAIL} мост не запустится: нет Stereo Mix или пары устройств")
        return
    import mic_bridge
    bridge = mic_bridge.MicBridge(mic_device=mic_i, render_device=r_i)
    try:
        bridge.start()
    except Exception as exc:  # noqa: BLE001
        check("запуск моста", False, str(exc))
        return
    check("мост запущен", True, "поговори 3 секунды...")
    time.sleep(3.0)
    st = bridge.status()
    check("речь идёт с микрофона", st["mic_peak"] > 0.003,
          f"пик {st['mic_peak']:.4f}" + ("" if st["mic_peak"] > 0.003 else " (тишина — говори!)"))

    phrase = os.path.join(ws, "out", "mp3", "mx_01.mp3")
    if os.path.exists(phrase):
        bridge.play_phrase(phrase)
        time.sleep(2.0)
        st2 = bridge.status()
        check("фраза идёт через мост", st2["out_peak"] > 0.01,
              f"выход {st2['out_peak']:.4f}")
    bridge.stop()

    print("\n=== 5. Что делать в игре ===")
    print(f"  1. В настройках голоса RedM выбери микрофон: «{mix_n}»")
    print("  2. В приложении: «Микрофон» -> «Включить мост» -> «Включить глобальные хоткеи»")
    print("  3. В игре жми Ctrl+Alt+1 ... Ctrl+Alt+0, Numpad, F1-F12")

    if "--full" in sys.argv:
        print("\n=== 6. Схожесть голоса (медленно) ===")
        gt = os.path.join(ws, "my_voice_ground_truth.wav")
        if not os.path.exists(gt):
            print("  {WARN} нет эталона из сырых записей — пропуск".replace("{WARN}", WARN))
        else:
            import subprocess
            python = sp.engine_python()
            script = os.path.join(ws, "tools", "voice_similarity.py")
            proc = subprocess.run([python, script, "--reference", gt,
                                   "--wav-dir", os.path.join(ws, "out", "wav")],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace")
            for line in proc.stdout.splitlines():
                if "Средняя схожесть" in line:
                    print(f"  {line}")


if __name__ == "__main__":
    main()
