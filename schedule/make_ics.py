#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор файла .ics (календарь) из простого текстового расписания.

Как пользоваться:
    python3 make_ics.py raspisanie.txt
    python3 make_ics.py raspisanie.txt -o moi_den.ics --start 2026-09-07 --weeks 12

Готовый .ics отправь себе на почту / в Telegram и открой на айфоне —
он сам предложит добавить события в Календарь.
"""

import argparse
import hashlib
import re
import sys
from datetime import date, datetime, timedelta, timezone

# сокращение дня -> (номер дня недели, код для календаря)
DAYS = {
    "пн": (0, "MO"),
    "вт": (1, "TU"),
    "ср": (2, "WE"),
    "чт": (3, "TH"),
    "пт": (4, "FR"),
    "сб": (5, "SA"),
    "вс": (6, "SU"),
}
ORDER = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

ALIASES = {
    "ежедневно": "пн-вс",
    "каждыйдень": "пн-вс",
    "будни": "пн-пт",
    "выходные": "сб,вс",
}


class ParseError(Exception):
    pass


def parse_days(token):
    """'пн-пт', 'пн,ср,пт', 'будни' -> отсортированный список сокращений дней."""
    token = token.lower().replace(" ", "")
    token = ALIASES.get(token, token)
    result = []
    for part in token.split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if a not in DAYS or b not in DAYS:
                raise ParseError(f"непонятный день недели: '{part}'")
            i, j = ORDER.index(a), ORDER.index(b)
            span = ORDER[i:j + 1] if i <= j else ORDER[i:] + ORDER[:j + 1]
            result.extend(span)
        else:
            if part not in DAYS:
                raise ParseError(f"непонятный день недели: '{part}'")
            result.append(part)
    if not result:
        raise ParseError("не указаны дни недели")
    # убираем дубли, сохраняем порядок пн..вс
    return [d for d in ORDER if d in result]


def parse_time(token):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", token)
    if not m:
        raise ParseError(f"непонятное время: '{token}' (нужно ЧЧ:ММ)")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise ParseError(f"такого времени не бывает: '{token}'")
    return h, mi


def parse_line(line):
    """'пн-пт 07:00-07:30 Подъём !10' -> словарь с описанием события."""
    alarm = None
    m = re.search(r"!(\d+)\s*$", line)
    if m:
        alarm = int(m.group(1))
        line = line[:m.start()].rstrip()

    parts = line.split(None, 2)
    if len(parts) < 3:
        raise ParseError("нужно 3 части: дни, время, название")
    days_tok, time_tok, title = parts

    days = parse_days(days_tok)
    if "-" not in time_tok:
        raise ParseError(f"непонятный интервал времени: '{time_tok}' (нужно ЧЧ:ММ-ЧЧ:ММ)")
    start_tok, end_tok = time_tok.split("-", 1)
    sh, sm = parse_time(start_tok)
    eh, em = parse_time(end_tok)

    return {
        "days": days,
        "start": (sh, sm),
        "end": (eh, em),
        "title": title.strip(),
        "alarm": alarm,
    }


def read_schedule(path):
    events, errors = [], []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                events.append(parse_line(line))
            except ParseError as e:
                errors.append(f"строка {n}: {e}\n    {raw.strip()}")
    if errors:
        raise ParseError("\n".join(errors))
    return events


def escape(text):
    """Спецсимволы, которые в формате .ics нужно экранировать."""
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n"))


def fold(line):
    """В .ics строка не должна быть длиннее 75 байт — режем и переносим пробелом."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    out, chunk = [], b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            out.append(chunk.decode("utf-8"))
            chunk = b
            limit = 74  # у продолжений в начале пробел
        else:
            chunk += b
    out.append(chunk.decode("utf-8"))
    return "\r\n ".join(out)


def first_occurrence(start_date, weekday):
    """Первая дата >= start_date, попадающая на нужный день недели."""
    return start_date + timedelta(days=(weekday - start_date.weekday()) % 7)


def build_ics(events, start_date, weeks, calendar_name):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//raspisanie//make_ics//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(calendar_name)}",
    ]

    for ev in events:
        anchor_wd = min(DAYS[d][0] for d in ev["days"])
        day0 = first_occurrence(start_date, anchor_wd)
        sh, sm = ev["start"]
        eh, em = ev["end"]
        dtstart = datetime(day0.year, day0.month, day0.day, sh, sm)
        dtend = datetime(day0.year, day0.month, day0.day, eh, em)
        if dtend <= dtstart:          # событие через полночь, например 23:00-01:00
            dtend += timedelta(days=1)

        uid_src = f"{ev['title']}|{ev['days']}|{ev['start']}|{ev['end']}|{start_date}"
        uid = hashlib.sha1(uid_src.encode("utf-8")).hexdigest()[:20]

        byday = ",".join(DAYS[d][1] for d in ev["days"])
        rrule = f"RRULE:FREQ=WEEKLY;BYDAY={byday}"
        if weeks:
            until = datetime.combine(start_date + timedelta(weeks=weeks), dtend.time())
            rrule += f";UNTIL={until.strftime('%Y%m%dT%H%M%S')}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@raspisanie",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dtend.strftime('%Y%m%dT%H%M%S')}",
            rrule,
            f"SUMMARY:{escape(ev['title'])}",
        ]
        if ev["alarm"] is not None:
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape(ev['title'])}",
                f"TRIGGER:-PT{ev['alarm']}M",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def main():
    p = argparse.ArgumentParser(description="Текстовое расписание -> файл .ics для Календаря")
    p.add_argument("input", help="файл с расписанием (например raspisanie.txt)")
    p.add_argument("-o", "--output", default="raspisanie.ics", help="куда сохранить .ics")
    p.add_argument("--start", help="с какой даты начать, ГГГГ-ММ-ДД (по умолчанию сегодня)")
    p.add_argument("--weeks", type=int, default=0,
                   help="сколько недель повторять (0 = бесконечно)")
    p.add_argument("--name", default="Мой день", help="название календаря")
    args = p.parse_args()

    start_date = date.fromisoformat(args.start) if args.start else date.today()

    try:
        events = read_schedule(args.input)
    except FileNotFoundError:
        sys.exit(f"Файл не найден: {args.input}")
    except ParseError as e:
        sys.exit(f"Ошибка в расписании:\n{e}")

    if not events:
        sys.exit("В файле нет ни одного события.")

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(events, start_date, args.weeks, args.name))

    print(f"Готово: {args.output} — событий: {len(events)}, старт с {start_date}")


if __name__ == "__main__":
    main()
