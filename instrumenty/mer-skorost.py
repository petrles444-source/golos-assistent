#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mer-skorost.py — не замедлил ли синтез ограничение потоков

ЗАЧЕМ. Я ограничила число потоков до одного на модель, чтобы
сервис не держал 40 потоков. Но ограничение потоков может замедлить
синтез: одна модель работает на одном ядре вместо многих. Если
замедлилось - значит, я поменяла одну проблему на другую, и об этом
надо сказать прямо, а не сделать вид, что выиграла.

КАК МЕРЯЮ
Прогоняю один и тот же набор фраз в двух процессах: с одним
потоком и без ограничения. Сравниваю время синтеза. Один и тот же
текст, один и тот же голос.

Запуск:
    python mer-skorost.py
"""
from __future__ import annotations

import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ЗДЕСЬ = Path(__file__).resolve().parent
ПАПКА = ЗДЕСЬ.parent / "modeli"
ФРАЗЫ = (
    "Проверка скорости синтеза голоса.",
    "Задача выполнена, отчёт отправлен лидеру студии.",
    "Проверка. Сорок два медведя, сто двадцать восемь граммов белка.",
    "Понял, берусь за работу прямо сейчас.",
    "Голосовое сообщение студии, слушай внимательно.",
)


def один_замер(потоки: str) -> list[float]:
    """Синтез всех фраз в отдельном процессе с заданным OMP_NUM_THREADS."""
    кусок = (
        "import os, sys, time, wave, tempfile\n"
        "sys.stdout.reconfigure(encoding='utf-8', errors='replace')\n"
        f"os.environ['OMP_NUM_THREADS'] = {потоки!r}\n"
        "os.environ['OMP_WAIT_POLICY'] = 'PASSIVE'\n"
        "from piper import PiperVoice\n"
        f"папка = r'{ПАПКА}'\n"
        "голос = PiperVoice.load(папка + r'\\ru_RU-irina-medium.onnx')\n"
        f"фразы = {ФРАЗЫ!r}\n"
        "времена = []\n"
        "путь = os.path.join(tempfile.gettempdir(), 'mer-skorost-proba.wav')\n"
        "for ф in фразы:\n"
        "    # пиперу нужен объект wave, а не просто файл: он зовёт\n"
        "    # setframerate, setsampwidth, setnchannels и writeframes.\n"
        "    # os.devnull и BytesIO для этого не годятся.\n"
        "    t0 = time.time()\n"
        "    with wave.open(путь, 'wb') as звук:\n"
        "        голос.synthesize_wav(ф, звук)\n"
        "    времена.append(time.time() - t0)\n"
        "print('\\n'.join('%.3f' % t for t in времена))\n"
    )
    итог = subprocess.run(
        [sys.executable, "-P", "-c", кусок],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=str(ЗДЕСЬ))
    строки = [с.strip() for с in итог.stdout.split() if с.strip()]
    числа = []
    for с in строки:
        try:
            числа.append(float(с.replace(",", ".")))
        except ValueError:
            continue
    if not числа:
        print(f"  потоки={потоки}: процесс не отдал ни одного времени")
        print(f"    {итог.stderr.strip()[:300]}")
    return числа


def главная() -> int:
    print("=" * 74)
    print("  ЗАМЕДЛИЛ ЛИ СИНТЕЗ ОГРАНИЧЕНИЕ ПОТОКОВ")
    print("=" * 74)
    print(f"  фраз для замера: {len(ФРАЗЫ)}, голос irina")
    print()

    один = один_замер("1")
    if not один:
        print("  замер с одним потоком провалился, вывод неполный")
        return 2
    много = один_замер("8")
    if not много:
        print("  замер без ограничения провалился, вывод неполный")
        return 2

    print(f"  {'фраза':>3} {'1 поток с':>11} {'8 потоков с':>13} {'разница':>10}")
    print("  " + "-" * 42)
    for i, (а, б) in enumerate(zip(один, много), 1):
        print(f"  {i:>3} {а:>11.3f} {б:>13.3f} {а - б:>+10.3f}")

    ср1 = statistics.mean(один)
    ср8 = statistics.mean(много)
    print("  " + "-" * 42)
    print(f"  среднее: 1 поток {ср1:.3f} с, 8 потоков {ср8:.3f} с")
    print(f"  разница: {ср1 - ср8:+.3f} с на фразу "
          f"({(ср1 / ср8 - 1) * 100:+.1f}%)")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(главная())
