#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mer-modeley.py — сколько стоит одна модель голоса: время и память

ЗАЧЕМ. Сервис держит в памяти сразу четыре модели piper, и это
основной вес. Вопрос: выгодно ли грузить их лениво, по первому
обращению? Ответ зависит от двух чисел, а они измеряются here.

ЧТО МЕРИЮ
1. Время загрузки одной модели в секундах.
2. Прирост памяти процесса на каждую модель.
3. Итог на все четыре голоса.

КАК МЕРИЮ ПАМЯТЬ
Через счётчик Windows GetProcessMemoryInfo для собственного
процесса. Первая версия прибора собирала структуру вручную в одну
строку и не собралась - SyntaaxError. Структура описана здесь
нормально, по полям.

Запуск:
    python mer-modeley.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

# Ограничение потоков ДО импорта onnxruntime - ровно как в сервисе.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ПАПКА = Path(__file__).resolve().parent.parent / "modeli"
ГОЛОСА = ("irina", "dmitri", "denis", "ruslan")


class СчётчикПамяти(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS из Windows."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def приватная_мб() -> float:
    """Приватная память моего процесса в мегабайтах.

    Тонкость, на которую ушла попытка: у этих двух функций Windows
    обязательно надо объявить прототипы. Без них Python передаёт
    указатель как 32-битное целое, он обрезается, функция
    возвращает ноль - и прибор либо падает, либо, что хуже, отдаёт
    правдоподобный ноль. Поэтому прототипы объявлены явно, а отказ
    чтения считается ошибкой, а не нулём.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(СчётчикПамяти),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int

    счётчик = СчётчикПамяти()
    счётчик.cb = ctypes.sizeof(СчётчикПамяти)
    кл = kernel32.GetCurrentProcess()
    if not кл:
        raise RuntimeError("GetCurrentProcess вернул пустой указатель")
    ок = psapi.GetProcessMemoryInfo(кл, ctypes.byref(счётчик), счётчик.cb)
    if not ок:
        raise RuntimeError(
            f"GetProcessMemoryInfo не отдал счётчик, код Windows "
            f"{ctypes.get_last_error()}")
    return счётчик.PagefileUsage / 1048576.0


def главная() -> int:
    print("=" * 74)
    print("  СКОЛЬКО СТОИТ ОДНА МОДЕЛЬ ГОЛОСА")
    print("=" * 74)
    print(f"  папка моделей: {ПАПКА}")
    print(f"  OMP_NUM_THREADS = {os.environ.get('OMP_NUM_THREADS')}")
    print()

    for имя in ГОЛОСА:
        if not (ПАПКА / f"ru_RU-{имя}-medium.onnx").exists():
            print(f"  {имя}: ФАЙЛА НЕТ, честно пропускаю")
    есть = [и for и in ГОЛОСА
            if (ПАПКА / f"ru_RU-{и}-medium.onnx").exists()]
    if not есть:
        print("  моделей на диске нет, мерить нечего")
        return 1

    from piper import PiperVoice                       # noqa: PLC0415

    print(f"  {'голос':>8} {'загрузка с':>12} {'память +МБ':>13}")
    print("  " + "-" * 36)
    было = приватная_мб()
    всего_времени = 0.0
    держать = []
    for имя in есть:
        t0 = time.time()
        голос = PiperVoice.load(str(ПАПКА / f"ru_RU-{имя}-medium.onnx"))
        dt = time.time() - t0
        всего_времени += dt
        стало = приватная_мб()
        держать.append(голос)          # держим, иначе память вернётся
        print(f"  {имя:>8} {dt:>11.1f}с {стало - было:>12.1f}")
        было = стало
    print("  " + "-" * 36)
    print(f"  итого времени на {len(есть)} голоса: {всего_времени:.1f} с")
    print(f"  память процесса сейчас: {приватная_мб():.1f} МБ")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(главная())
