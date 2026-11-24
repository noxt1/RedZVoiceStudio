"""Проверка темпа и пауз (Этап C.7.7)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from voice_post import add_pauses
import voice_tone


def test_speed():
    print("=== Параметры тона ===")
    for name in ("NEUTRAL", "AGGRESSIVE", "FRIENDLY", "ENERGETIC"):
        p = getattr(voice_tone, name)
        sp = p["speed"]
        rp = p["repetition_penalty"]
        tp = p["temperature"]
        print(f"{name:11} speed={sp} rep={rp} temp={tp}")
        assert sp <= 1.0, f"{name}: speed>1.0 будет тараторить"
        assert rp >= 8.0, f"{name}: repetition_penalty<8 будет зацикливать"
        assert tp <= 0.82, f"{name}: temperature>0.82 будет кашей"


def test_pauses():
    print()
    print("=== Паузы ===")
    cases = [
        "Hola que tal me dices como estas",
        "Eres un maldito cabron no me jodas y vete de aqui ahora mismo",
        "¿Qué tal mi juego?",
    ]
    for s in cases:
        out = add_pauses(s)
        print(f"  {s!r}")
        print(f"    -> {out!r}")
        assert out.endswith((".", "!", "?", "¡", "…")), "нет точки в конце"
        # Длинные фразы должны быть разбиты
        if len(s.split()) > 14:
            assert out.count(".") >= 2, "длинная фраза не разбита на предложения"


def test_tone_params_override():
    print()
    print("=== _tone_params не портит rep/speed ===")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lt", os.path.join(os.path.dirname(__file__), "..", "tools",
                           "live_translate.py"))
    # Не импортируем движок целиком (тяжёлые зависимости) — читаем исходник
    path = os.path.join(os.path.dirname(__file__), "..", "tools",
                        "live_translate.py")
    src = open(path, encoding="utf-8").read()
    i = src.find("def _tone_params")
    body = src[i:i + 2500]
    assert '"repetition_penalty"] = 10.0' in body, "rep не фиксируется на 10"
    assert "max(3.0, min(9.0" not in body, "старая формула снижения осталась"
    assert "min(1.0, max(0.92" in body, "speed не ограничен сверху 1.0"
    print("OK: rep=10.0 фиксирован, speed ограничен 0.92..1.0")


if __name__ == "__main__":
    test_speed()
    test_pauses()
    test_tone_params_override()
    print()
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")