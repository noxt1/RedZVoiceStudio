"""Проверка скриншота Qt-интерфейса без просмотра человеком.

Считает: долю непустых пикселей, число различных цветов, наличие
акцентных цветов (палитра RedZ), яркость по зонам (сайдбар / контент).
Так можно отличить «интерфейс отрисован» от «чёрное окно / белый лист».
"""

from __future__ import annotations

import os
import sys

from PIL import Image

# Ожидаемые фирменные цвета (из Theme.qml)
ACCENT = (79, 195, 247)        # #4FC3F7
INCOMING = (169, 139, 255)     # #A98BFF
SUCCESS = (74, 222, 155)       # #4ADE9B
BG = (7, 11, 17)               # #070B11
SURFACE = (13, 20, 29)         # #0D141D


def near(px, target, tol=26) -> bool:
    return (abs(px[0] - target[0]) <= tol
            and abs(px[1] - target[1]) <= tol
            and abs(px[2] - target[2]) <= tol)


def main() -> int:
    path = sys.argv[1]
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()

    total = w * h
    colors = im.getcolors(maxcolors=total) or []
    n_colors = len(colors)

    accent = incoming = success = bg = surface = 0
    bright = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            p = px[x, y]
            if near(p, ACCENT):
                accent += 1
            if near(p, INCOMING):
                incoming += 1
            if near(p, SUCCESS):
                success += 1
            if near(p, BG, 10):
                bg += 1
            if near(p, SURFACE, 10):
                surface += 1
            if sum(p) > 250:
                bright += 1

    sampled = (w // 2 + 1) * (h // 2 + 1)

    # зоны: сайдбар (0..236) и контент
    def zone_avg(x0, x1):
        r = g = b = n = 0
        for y in range(0, h, 3):
            for x in range(x0, min(x1, w), 3):
                p = px[x, y]
                r += p[0]; g += p[1]; b += p[2]; n += 1
        return (r // max(n, 1), g // max(n, 1), b // max(n, 1))

    sidebar_avg = zone_avg(0, 236)
    content_avg = zone_avg(240, w)

    print(f"размер:        {w}x{h}")
    print(f"уник. цветов:  {n_colors}")
    print(f"акцент:        {accent / sampled * 100:.2f}%")
    print(f"incoming:      {incoming / sampled * 100:.2f}%")
    print(f"success:       {success / sampled * 100:.2f}%")
    print(f"фон:           {bg / sampled * 100:.2f}%")
    print(f"поверхность:   {surface / sampled * 100:.2f}%")
    print(f"светлые px:    {bright / sampled * 100:.2f}%")
    print(f"сайдбар avg:   {sidebar_avg}")
    print(f"контент avg:   {content_avg}")

    problems = []
    if n_colors < 40:
        problems.append(f"слишком мало цветов ({n_colors}) — похоже на пустой экран")
    if accent / sampled < 0.0005:
        problems.append("акцентный цвет почти не виден")
    if bright / sampled < 0.002:
        problems.append("нет светлого текста — вероятно пустой фон")
    if bg / sampled < 0.15:
        problems.append("мало фонового цвета темы")

    if problems:
        print("\nПРОБЛЕМЫ:")
        for p in problems:
            print("  -", p)
        return 1
    print("\nOK: интерфейс отрисован")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())