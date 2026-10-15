#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Пример подключения голосового помощника к любому агенту.

Файл самодостаточный: стандартная библиотека и ничего больше.
Его можно скопировать в свой проект и вызывать из агента.

Как это выглядит у агента: агент сформулировал фразу, отдал её сюда,
здесь появился звуковой файл, агент его озвучил. Или агент отдал фразу
по сети в формате JSON — тогда подойдёт вызов send_text().

Запуск для проверки:
    python primer/primer_python.py
    python primer/primer_python.py --текст "Своими словами" --голос DENIS
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

БАЗА = "http://127.0.0.1:18905"

# Адреса сервиса на русском. Многие HTTP-клиенты не умеют отправлять
# кириллицу в адресе и падают с UnicodeEncodeError. Поэтому здесь
# используются латинские адреса /state и /say — они равнозначны.
АДРЕС_СОСТОЯНИЕ = "state"
АДРЕС_СКАЗАТЬ = "say"

# Окно длины голосового сообщения. Короче трёх секунд — слишком коротко,
# дольше двадцати пяти — человек не дослушает.
ОКНО_СЕКУНД = (3, 25)

# Темп словами, а не числами.
ТЕМПЫ = {"медленно": 0.75, "нейтрально": 1.0, "быстро": 1.25}


def состояние(база=БАЗА):
    """Жив ли сервис и какие голоса есть. Ничего не требует."""
    try:
        with urllib.request.urlopen(f"{база}/{АДРЕС_СОСТОЯНИЕ}", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"жив": False, "ошибка": f"код {e.code}"}
    except Exception as e:
        return {"жив": False, "ошибка": type(e).__name__}


def сказать(текст, голос="IRINA", темп=None, играть=False, база=БАЗА):
    """Просит сервис произнести фразу. Возвращает словарь с результатом."""
    скорость = ТЕМПЫ.get(темп) if темп else None
    # urlencode кодирует и имена параметров, и их значения. Это важно:
    # без него клиент падает на кириллице в адресе ещё ДО запроса.
    поля = {"агент": голос, "текст": текст,
            "играть": "1" if играть else "0"}
    if скорость:
        поля["скорость"] = f"{скорость:.3f}"
    адрес = f"{база}/{АДРЕС_СКАЗАТЬ}?{urllib.parse.urlencode(поля)}"
    try:
        with urllib.request.urlopen(адрес, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        сырой = e.read().decode("utf-8", "replace")
        try:
            return json.loads(сырой)
        except Exception:
            return {"ок": False, "ошибка": f"код {e.code}", "тело": сырой[:200]}
    except Exception as e:
        return {"ок": False, "ошибка": type(e).__name__}


def окно_длины(секунды):
    """Честный вердикт по длине, словами."""
    низ, верх = ОКНО_СЕКУНД
    if секунды < низ:
        return "слишком коротко"
    if секунды > верх:
        return "слишком долго"
    return "в норме"


def озвучить(файл):
    """Проигрывает готовый звук средствами системы."""
    файл = str(файл)
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(файл, winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        subprocess.run(["afplay", файл], check=False)
    else:
        subprocess.run(["aplay", "-q", файл], check=False)


def главная():
    п = argparse.ArgumentParser(description="Проверка голосового помощника")
    п.add_argument("--текст", default=None)
    п.add_argument("--голос", default="IRINA")
    п.add_argument("--темп", choices=list(ТЕМПЫ), default=None)
    п.add_argument("--база", default=БАЗА)
    п.add_argument("--играть", action="store_true")
    а = п.parse_args()

    текст = а.текст or ("Это проверка голосового помощника. "
                        "Если вы это слышите, значит всё работает.")

    print("1. Спрашиваю состояние сервиса")
    сост = состояние(а.база)
    if not сост.get("жив"):
        print(f"   сервис не отвечает: {сост.get('ошибка')}")
        print("   Запустите его: python golos_servis.py")
        return 2
    print(f"   жив, порт {сост.get('порт')}")
    print(f"   голоса: {', '.join(сост.get('агенты', []))}")
    print(f"   в памяти: {сост.get('загружены_модели') or 'пусто, ленивая загрузка'}")

    print()
    print(f"2. Прошу сказать голосом {а.голос}")
    t0 = time.time()
    рез = сказать(текст, а.голос, а.темп, а.играть, а.база)
    прошло = time.time() - t0
    print(f"   прошло {прошло:.1f} с")
    for ключ in ("ок", "озвучка_секунд", "синтез_секунд", "всего_секунды",
                 "из_кэша", "байт", "движок", "плеер", "ошибка"):
        if ключ in рез:
            print(f"   {ключ}: {рез[ключ]}")

    if not рез.get("ок"):
        print()
        print("   НЕ ПОДТВЕРЖДЕНО: сервис не отдал файл.")
        return 3

    длина = рез.get("озвучка_секунд")
    if длина is not None:
        print(f"   длина звука: {окно_длины(float(длина))}")
    else:
        print("   длина звука: не измерена (для mp3 нужен декодер)")

    if а.играть and рез.get("файл"):
        print()
        print("3. Озвучиваю")
        озвучить(рез["файл"])
        print("   готово")

    print()
    print("ГОТОВО. Проверка подтверждена живым запросом.")
    return 0


if __name__ == "__main__":
    sys.exit(главная())