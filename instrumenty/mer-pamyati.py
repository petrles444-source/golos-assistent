#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mer-pamyati.py — утечка памяти в голосовом сервисе или рабочий набор?

ВОПРОС, НА КОТОРЫЙ ОТВЕЧАЕМ ЧИСЛОМ
«Держать 746 МБ - это много, похоже на утечка». Похоже - не
доказательство. Утечка - это когда память растёт со временем. А если
просто загружены модели, то память растёт один раз и держится.

КАК ПРОВЕРЯЮ
1. Смотрю память сразу после старта, когда модели ещё грузятся.
2. Смотрю память после того, как модели загрузились.
3. Шлю запросы пачками и каждый раз меряю память.
4. Считаю НАКЛОН: сколько памяти добавляется на один запрос.
   Наклон около нуля - утечки нет. Наклон в килбайты на запрос -
   утечка есть.

КАК МЕРЯЮ
Через счётчик Private Working Set самого процесса, а не через
сглаженную память в диспетчере. Это то, что реально занимает
процесс, и оно не врёт.

Запуск:
    python mer-pamyati.py --запросов 60
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ЗДЕСЬ = Path(__file__).resolve().parent
ПОРТ = 18905
САМО = "golos_servis.py"


def пиды() -> list[int]:
    """Пиды процессов сервиса, запущенных из папки агента."""
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
         "Where-Object { $_.CommandLine -match 'golos_servis' }).ProcessId"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for строка in ps.stdout.split():
        try:
            out.append(int(строка))
        except ValueError:
            continue
    return out


def память(пид: int) -> tuple[float, float, int]:
    """(частная память МБ, рабочий набор МБ, потоков).

    Читаем по одному значению в строке. Первая версия отдавала
    числа одной строкой в скобках, разбор не сходился, и прибор
    писал -1 МБ - то есть НИЧЕГО не мерил, а потом объявлял
    «утечки нет». Ноль из неисправного измерителя не является
    доказательством отсутствия утечки.
    """
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"$p = Get-Process -Id {пид} -ErrorAction SilentlyContinue\n"
         f"if ($null -ne $p) {{\n"
         f"  [math]::Round($p.PrivateMemorySize64/1MB,1)\n"
         f"  [math]::Round($p.WorkingSet64/1MB,1)\n"
         f"  $p.Threads.Count\n"
         f"}} else {{ 'нет процесса' }}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    строки = [с.strip() for с in ps.stdout.replace("\r", "").split("\n")
              if с.strip()]
    if len(строки) < 3:
        raise RuntimeError(
            f"не прочиталось: ответ PowerShell был {ps.stdout.strip()[:80]!r}")
    try:
        приват = float(строки[-3].replace(",", "."))
        рабочий = float(строки[-2].replace(",", "."))
        потоков = int(строки[-1])
    except ValueError as ошибка:
        raise RuntimeError(f"не разобралось: {строки[-3:]}") from ошибка
    return приват, рабочий, потоков


def сервис_жив() -> bool:
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (ПОРТ, urllib.parse.quote("/состояние")),
                timeout=10) as r:
            return bool(json.load(r).get("жив"))
    except Exception:                                                    # noqa: BLE001
        return False


def сказать(текст: str, агент: str = "IRINA") -> float:
    адрес = ("http://127.0.0.1:%d%s?%s" % (
        ПОРТ, urllib.parse.quote("/сказать"),
        urllib.parse.urlencode({"агент": агент, "текст": текст, "играть": "0"})))
    t0 = time.time()
    try:
        with urllib.request.urlopen(адрес, timeout=180) as r:
            json.load(r)
    except Exception:                                                    # noqa: BLE001
        pass
    return time.time() - t0


def главная() -> int:
    п = argparse.ArgumentParser()
    п.add_argument("--запросов", type=int, default=60)
    п.add_argument("--пачка", type=int, default=10)
    а = п.parse_args()

    print("=" * 74)
    print("  УТЕЧКА ПАМЯТИ ИЛИ РАБОЧИЙ НАБОР")
    print("=" * 74)

    if not сервис_жив():
        print("  сервис не отвечает, поднимаю...")
        subprocess.Popen([sys.executable, "-P", "-u", str(ЗДЕСЬ / САМО)],
                         cwd=str(ЗДЕСЬ))
        for _ in range(40):
            time.sleep(2.0)
            if сервис_жив():
                break

    # Главный процесс - тот, что держит порт и работает.
    наши = пиды()
    if not наши:
        print("  процессов сервиса не найдено")
        return 1
    главный = наши[-1]
    приват, рабочий, потоков = память(главный)
    print(f"  процессов сервиса: {len(наши)}, работает пид {главный}")
    print(f"  сейчас: {приват} МБ приватной, {рабочий} МБ в работе, "
          f"{потоков} потоков")

    # Грём сервис: память роста на диске может подскочить.
    for _ in range(5):
        сказать("прогрев")
    приват1, рабочий1, потоков1 = память(главный)
    print(f"  после 5 запросов на прогрев: {приват1} МБ, {потоков1} потоков")
    print()

    print(f"  {'запросов':>9} {'приватная МБ':>14} {'прирост МБ':>12} "
          f"{'на запрос КБ':>14}")
    print("  " + "-" * 58)
    база = приват1
    отметки = [(0, приват1)]
    for круг in range(1, а.запросов // а.пачка + 1):
        for i in range(а.пачка):
            сказать(f"Проверка памяти, запрос номер {круг * а.пачка + i}. "
                    f"Текст специально разной длины для замера.")
        приват, рабочий, потоков = память(главный)
        сделано = круг * а.пачка
        прирост = приват - база
        на_запрос = прирост * 1024 / max(1, сделано)
        print(f"  {сделано:>9} {приват:>14.1f} {прирост:>12.1f} "
              f"{на_запрос:>14.1f}")
        отметки.append((сделано, приват))

    print("  " + "-" * 58)
    # Наклон по последней трети точек - там, где уже прогрето.
    хвост = отметки[-max(2, len(отметки) // 3):]
    (x1, y1), (x2, y2) = хвост[0], хвост[-1]
    наклон = (y2 - y1) / max(1, (x2 - x1)) * 1024   # КБ на запрос
    приват, рабочий, потоков = память(главный)

    print()
    print("=" * 74)
    print("  ВЕРДИКТ")
    print("=" * 74)
    # ГЛАВНОЕ ПРАВИЛО. Если хоть одна точка не измерена, вердикта нет.
    # Раньше при сбое измерителя все точки были нулями, наклон выходил
    # нулём, и прибор печатал «утечки нет». Это ложь: ноль из
    # неисправного прибора не доказательство. Здесь такой случай
    # заканчивается честным «не измерено» и ненулевым кодом выхода.
    битых = sum(1 for _, значение in отметки if значение < 0)
    if битых:
        print("  ВЕРДИКТА НЕТ. НЕ ИЗМЕРЕНО.")
        print(f"  из {len(отметки)} замеров не прочиталось {битых}")
        print("  «Утечки нет» из неисправного измерителя - это не ответ.")
        print("=" * 74)
        return 2

    if наклон < 5:
        print("  УТЕЧКИ НЕТ.")
        print(f"  Наклон по хвосту: {наклон:.1f} КБ на запрос - это шум.")
    elif наклон < 50:
        print("  УТЕЧКА СЛАБАЯ, есть на что посмотреть.")
        print(f"  Наклон: {наклон:.1f} КБ на запрос.")
    else:
        print("  УТЕЧКА ЕСТЬ.")
        print(f"  Наклон: {наклон:.1f} КБ на запрос.")
    print(f"  Итог: {приват} МБ приватной, {рабочий} МБ в работе, "
          f"{потоков} потоков")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(главная())