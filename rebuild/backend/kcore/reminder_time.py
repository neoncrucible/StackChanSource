"""Deterministic local-calendar resolution. A language model never supplies 'now'."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")


@dataclass(frozen=True)
class Resolution:
    due: datetime | None = None
    question: str = ""
    day: str = ""
    clock: str = ""
    issue: str = ""


def temporal_numbers(value: str) -> str:
    text = value.casefold().replace("a.m.", "am").replace("p.m.", "pm")
    text = re.sub(r"\b([ap])\s+m\b", r"\1m", text)
    text = re.sub(r"\bhalf an? hour\b", "30 minutes", text)
    text = re.sub(r"\b(?:a|an) (second|minute|hour|day)\b", r"1 \1", text)
    for tens, name in ((20, "twenty"), (30, "thirty"), (40, "forty"), (50, "fifty"), (60, "sixty")):
        for n in range(1, 10):
            text = re.sub(rf"\b{name}[ -]{ONES[n]}\b", str(tens + n), text)
        text = re.sub(rf"\b{name}\b", str(tens), text)
    for n in range(19, -1, -1):
        text = re.sub(rf"\b{ONES[n]}\b", str(n), text)
    return text.strip(" .?!,")


def clock_context(timezone_name: str, now: datetime | None = None) -> dict:
    current = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone_name))
    return {"local_datetime": current.isoformat(timespec="seconds"),
            "weekday": current.strftime("%A"), "timezone": timezone_name,
            "tomorrow": (current.date() + timedelta(days=1)).isoformat()}


def spoken_due(value: datetime, timezone_name: str) -> str:
    local = value.astimezone(ZoneInfo(timezone_name))
    return f"{local:%A} {local.day} {local:%B %Y}, {local:%H:%M} {local:%Z}"


def resolve_when(value: str, *, now: datetime, timezone_name: str, day_hint: str = "", clock_hint: str = "") -> Resolution:
    if now.tzinfo is None:
        raise ValueError("current time must be timezone-aware")
    zone = ZoneInfo(timezone_name)
    local_now = now.astimezone(zone)
    text = temporal_numbers(value)
    relative = re.fullmatch(r"(?:in |for )?(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|days?)(?: time)?", text)
    if relative:
        amount = float(relative[1]) * {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[relative[2].rstrip("s")]
        if not 5 <= amount <= 366 * 86400:
            return Resolution(question="Choose a delay from five seconds to one year.", issue="range")
        return Resolution(due=now.astimezone(UTC) + timedelta(seconds=amount))

    chosen: date | None = date.fromisoformat(day_hint) if day_hint else None
    day_found = False
    if re.search(r"\btomorrow\b", text):
        chosen, day_found = local_now.date() + timedelta(days=1), True
        text = re.sub(r"\btomorrow\b", "", text)
    elif re.search(r"\b(today|tonight)\b", text):
        chosen, day_found = local_now.date(), True
        text = re.sub(r"\b(today|tonight)\b", "", text)
    else:
        weekday = re.search(r"\b(next )?(" + "|".join(WEEKDAYS) + r")\b", text)
        numeric = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b", text)
        named = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)? (" + "|".join(MONTHS) + r")(?: (\d{4}))?\b", text)
        try:
            if weekday:
                delta = (WEEKDAYS.index(weekday[2]) - local_now.weekday()) % 7
                # A named weekday means its next occurrence. Read back the date.
                if delta == 0 or weekday[1]:
                    delta = delta or 7
                chosen = local_now.date() + timedelta(days=delta)
                text = text[:weekday.start()] + text[weekday.end():]
                day_found = True
            elif numeric:
                chosen = date.fromisoformat(numeric[1]) if "-" in numeric[1] else datetime.strptime(numeric[1], "%d/%m/%Y").date()
                text = text[:numeric.start()] + text[numeric.end():]
                day_found = True
            elif named:
                year = int(named[3]) if named[3] else local_now.year
                chosen = date(year, MONTHS.index(named[2]) + 1, int(named[1]))
                text = text[:named.start()] + text[named.end():]
                day_found = True
        except ValueError:
            return Resolution(question="That date doesn't exist. Which date and time should I use?", issue="date")

    text = re.sub(r"\b(?:on|at|please|o'clock)\b", "", text).strip(" ,")
    text = re.sub(r"\s+", " ", text)
    if text in {"am", "pm", "in the morning", "in the evening", "in the afternoon", "first", "second"} and clock_hint:
        text = clock_hint + " " + text
    if not text and clock_hint and day_found:
        text = clock_hint
    if not text:
        question = f"What time on {chosen:%A} {chosen.day} {chosen:%B}?" if chosen else "What date and time should I remind you?"
        return Resolution(question=question, day=chosen.isoformat() if chosen else "", issue="missing_time")

    text = text.replace("in the morning", "am").replace("in the afternoon", "pm").replace("in the evening", "pm")
    text = text.replace("noon", "12:00 pm").replace("midnight", "00:00")
    text = re.sub(r"\bhalf past (\d{1,2})", r"\1:30", text)
    text = re.sub(r"\bquarter past (\d{1,2})", r"\1:15", text)
    text = re.sub(r"\bquarter to (\d{1,2})", lambda m: f"{(int(m[1])-1) % 12 or 12}:45", text)
    match = re.fullmatch(r"(\d{1,2})(?:(:|\.| )(\d{2}))?\s*(am|pm)?(?:\s+(first|second))?", text)
    if not match:
        return Resolution(question="Give me a time such as 7 pm or 19:30, with a date if needed.", day=chosen.isoformat() if chosen else "", issue="time")
    hour, minute, meridian, occurrence = int(match[1]), int(match[3] or 0), match[4], match[5]
    chosen = chosen or local_now.date()
    clock_text = f"{hour}:{minute:02d}" if match[2] else str(hour)
    if minute > 59 or hour > 23 or (meridian and not 1 <= hour <= 12):
        return Resolution(question="That time isn't valid. What time should I use?", day=chosen.isoformat(), issue="time")
    if not meridian and 1 <= hour <= 12 and not (match[2] and match[1].startswith("0")):
        # Explicit 24-hour afternoon values and leading-zero clock values are unambiguous.
        return Resolution(question=f"Do you mean {hour}:{minute:02d} am or pm?", day=chosen.isoformat(), clock=clock_text, issue="meridian")
    if meridian:
        hour = hour % 12 + (12 if meridian == "pm" else 0)
    wall = datetime.combine(chosen, time(hour, minute))
    candidates = []
    for fold in (0, 1):
        instant = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == wall and instant not in candidates:
            candidates.append(instant)
    remembered_clock = f"{hour:02d}:{minute:02d}" if hour == 0 or hour > 12 else f"{hour % 12 or 12}:{minute:02d} {'pm' if hour >= 12 else 'am'}"
    if not candidates:
        return Resolution(question="The clocks skip that local time. Choose another time.", day=chosen.isoformat(), issue="dst_gap")
    if len(candidates) == 2 and occurrence is None:
        return Resolution(question="That time occurs twice when the clocks change. Say the time followed by first or second.", day=chosen.isoformat(), clock=remembered_clock, issue="dst_fold")
    due = candidates[1 if occurrence == "second" and len(candidates) == 2 else 0]
    if due <= now.astimezone(UTC):
        return Resolution(question="That time has passed. Which future date should I use?", clock=remembered_clock, issue="past")
    if due - now.astimezone(UTC) > timedelta(days=366):
        return Resolution(question="Choose a date within the next year.", issue="range")
    return Resolution(due=due)


def split_reminder_request(text: str) -> tuple[str, str] | None:
    """Return (task, temporal phrase) only for an explicit reminder/timer request."""
    source = text.strip().rstrip(".!?")
    match = re.fullmatch(r"(?:please )?(.*?)\bremind me\s+(.*)", source, re.I)
    if match:
        prefix, rest = match[1].strip(), match[2].strip()
        # A temporal clause before 'remind me' is explicit: tomorrow remind me ...
        if prefix:
            task = re.sub(r"^(?:to |that |i need to )", "", rest, flags=re.I)
            tail = re.search(r"\s+(at\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|half|quarter|noon|midnight)\b.*)$", task, re.I)
            if tail:
                return task[:tail.start()].strip(), prefix + " " + tail[1]
            return task, prefix
        front = re.fullmatch(r"((?:at|on|in|tomorrow|today|next)\b.*?)\s+(?:to|that|i need to)\s+(.+)", rest, re.I)
        if front:
            return front[2].strip(), front[1].strip()
        task = re.sub(r"^(?:to |that |i need to )", "", rest, flags=re.I)
        number = r"(?:\d+|" + "|".join(ONES[1:]) + r"|twenty|thirty|forty|fifty|half|quarter|noon|midnight)"
        days = "|".join(WEEKDAYS)
        tail = re.search(r"\s+((?:tomorrow|today|tonight|at\s+" + number + r"|in\s+(?:" + number + r"|a|an)|on\s+(?:\d+|" + days + r")|next\s+(?:" + days + r"))\b.*)$", task, re.I)
        if tail:
            return task[:tail.start()].strip(), tail[1].strip()
        return task, ""
    timer = re.fullmatch(r"(?:please )?(?:set|start) (?:a )?timer (?:for )?(.+?)(?: (?:called|to) (.+))?", source, re.I)
    if timer:
        return timer[2] or "Timer finished", timer[1]
    return None
