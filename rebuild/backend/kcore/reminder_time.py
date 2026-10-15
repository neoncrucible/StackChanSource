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
    text = value.casefold().replace("’", "'").replace("a.m.", "am").replace("p.m.", "pm")
    text = re.sub(r"\b([ap])\s+m\b", r"\1m", text)
    text = re.sub(r"\b(?:a )?quarter (?:of )?an? hour\b", "15 minutes", text)
    text = re.sub(r"\ban? hour and a half\b", "90 minutes", text)
    text = re.sub(r"\b(\d+|two|three|four) and a half hours?\b", r"\1 hours and 30 minutes", text)
    text = re.sub(r"\bhalf an? hour\b", "30 minutes", text)
    text = re.sub(r"\b(?:a|an) (second|minute|hour|day|week)\b", r"1 \1", text)
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
    if re.search(r"\b(?:every|each|daily|weekly|monthly|yearly|weekdays|weekends)\b", text):
        return Resolution(question="Repeating reminders aren't available yet, Boss. What date and time should I use for a single reminder?", issue="recurrence")
    text = re.sub(r"^when (?:it(?:'s| is)|the time is)\s+", "at ", text)
    if re.search(r"\b(?:when|whenever|if|once|as soon as|after (?:i|you|the|my))\b", text):
        return Resolution(question="I can't detect that condition from here, Boss. What date and time should I remind you instead?", issue="condition")
    text = re.sub(r"\b(?:from now|later|(?:of )?time)$", "", text).strip()
    text = re.sub(r"\b(\d+)-(second|minute|hour|day|week)s?\b", r"\1 \2", text)
    text = re.sub(r"^(?:in|for|after)\s+(?=\d)", "", text)
    units = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}
    duration = r"\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?|weeks?)"
    relative = re.fullmatch(duration + r"(?:(?:\s+and\s+|\s*,\s*|\s+)" + duration + r")*", text)
    if relative:
        amount = sum(float(n) * units[unit.rstrip("s")] for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|days?|weeks?)", text))
        if not 5 <= amount <= 366 * 86400:
            return Resolution(question="Choose a delay from five seconds to one year.", issue="range")
        return Resolution(due=now.astimezone(UTC) + timedelta(seconds=amount))

    chosen: date | None = date.fromisoformat(day_hint) if day_hint else None
    day_found = False
    if re.search(r"\b(?:the )?day after tomorrow\b", text):
        chosen, day_found = local_now.date() + timedelta(days=2), True
        text = re.sub(r"\b(?:the )?day after tomorrow\b", "", text)
    elif re.search(r"\btomorrow\b", text):
        chosen, day_found = local_now.date() + timedelta(days=1), True
        text = re.sub(r"\btomorrow\b", "", text)
    elif re.search(r"\b(today|tonight)\b", text):
        chosen, day_found = local_now.date(), True
        text = re.sub(r"\b(today|tonight)\b", "", text)
    else:
        text = re.sub(r"\bthis (morning|afternoon|evening)\b", r"today in the \1", text)
        if "today" in text:
            chosen, day_found = local_now.date(), True
            text = text.replace("today", "")
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

    text = re.sub(r"\b(?:(?:in the|in|the) )?morning\b", "am", text)
    text = re.sub(r"\b(?:(?:in the|in|the) )?(?:afternoon|evening)\b", "pm", text)
    if text in {"am", "pm"} and not clock_hint:
        return Resolution(question="What time in the morning?" if text == "am" else "What time in the afternoon or evening?",
            day=chosen.isoformat() if chosen else "", clock=text, issue="missing_time")
    if clock_hint in {"am", "pm"} and re.fullmatch(r"\d{1,2}(?::\d{2})?", text):
        text += " " + clock_hint
    text = re.sub(r"^(am|pm) (\d{1,2}(?::\d{2})?)$", r"\2 \1", text)
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


def request_body(text: str) -> str:
    """Remove spoken courtesies without rewriting the task, numbers or negation."""
    source = text.replace("’", "'").strip(" .!?,")
    for _ in range(5):
        previous = source
        source = re.sub(r"^(?:(?:hey|okay|ok)\s+)?(?:kadence|kade)\b[, ]*|^please\s+", "", source, flags=re.I)
        source = re.sub(r"^(?:would you mind|do you mind|(?:can|could|would|will) you(?: please)?|i(?:'d like| want| need) you to)\s+", "", source, flags=re.I)
        source = re.sub(r"^(reminding|setting|creating|starting)\b", lambda m: {"reminding":"remind", "setting":"set", "creating":"create", "starting":"start"}[m[1].lower()], source, flags=re.I)
        source = re.sub(r"[, ]+(?:for me(?: please)?|please|thanks|thank you)$", "", source, flags=re.I).strip(" ,")
        if source == previous: break
    return source


NUMBER = r"(?:\d+|" + "|".join(ONES[1:]) + r"|twenty|thirty|forty|fifty|half|quarter|noon|midnight|a|an)"
DAY = "|".join(WEEKDAYS)
TEMPORAL_START = (r"(?:tomorrow|today|tonight|the day after tomorrow|day after tomorrow|this (?:morning|afternoon|evening)|"
                  r"at\s+" + NUMBER + r"|(?:in|after)\s+" + NUMBER + r"|on\s+(?:\d+|" + DAY + r")|"
                  r"(?:next\s+)?(?:" + DAY + r")|when|whenever|if|once|every|each)")


def split_reminder_request(text: str) -> tuple[str, str] | None:
    """Fast paths for common requests; unfamiliar wording goes to the planner.

    Return only a task and the owner's time words. The local calendar resolves
    them, including ambiguity and unsupported events, before any write.
    """
    source = request_body(text)
    if re.match(r'^(?:if|suppose|imagine|pretend)\b', source, re.I): return None
    verbs = (r"(?:remind me|(?:set|create|add|schedule|make)(?: me)?(?: up)? (?:a |an?other |my )?reminder(?: for me)?|"
             r"(?:don't|do not) let me forget|make sure i (?:don't|do not) forget|"
             r"(?:i need|i want|i'd like) (?:a )?reminder|nudge me|ping me|alert me|notify me|let me know)")
    match = re.fullmatch(r"(?:(" + TEMPORAL_START + r"\b.*?)\s+)?" + verbs + r"(?:\s+(.*))?", source, re.I)
    if match:
        prefix, rest = (match[1] or "").strip(" ,"), (match[2] or "").strip()
        if re.match(r'^(?:nudge me|ping me|alert me|notify me|let me know)\b', source, re.I) and not re.search(TEMPORAL_START + r'\b', rest, re.I):
            return None
        rest = re.sub(r"^(?:for|about)\s+(?=" + TEMPORAL_START + r"\b)", "", rest, flags=re.I)
        if prefix:
            task = re.sub(r"^(?:to |that |i need to |about )", "", rest, flags=re.I)
            tail = re.search(r"\s+(at\s+" + NUMBER + r"\b.*)$", task, re.I)
            return (task[:tail.start()].strip(), prefix + " " + tail[1]) if tail else (task, prefix)
        front = re.fullmatch(r"(" + TEMPORAL_START + r"\b.*?)\s+(?:to|that|i need to|about)\s+(.+)", rest, re.I)
        if front:
            return front[2].strip(), front[1].strip()
        if re.match(r"^" + TEMPORAL_START + r"\b", rest, re.I):
            return "", rest
        task = re.sub(r"^(?:to |that |i need to |about |for )", "", rest, flags=re.I)
        tail = re.search(r"\s+(" + TEMPORAL_START + r"\b.*)$", task, re.I)
        if tail:
            return task[:tail.start()].strip(), tail[1].strip()
        # Bare clock after 'for' is common: set a reminder for 7 pm.
        if re.fullmatch(NUMBER + r"(?::\d{2})?\s*(?:am|pm)", task, re.I):
            return "", task
        return task, ""
    timer = re.fullmatch(r"(?:set|start|begin) (?:me )?(?:a )?timer (?:for )?(.+?)(?: (?:called|to) (.+))?", source, re.I)
    if timer:
        return timer[2] or "Timer finished", timer[1]
    timer = re.fullmatch(r"(?:set|start|begin) (?:a )?(.+?) timer(?: (?:for|called|to) (.+))?", source, re.I)
    if timer:
        return timer[2] or "Timer finished", timer[1]
    return None


def allows_reminder_tool(text: str) -> bool:
    """Broad request authority for semantic routing, never a model-set flag."""
    source = request_body(text).casefold()
    if re.match(r"^(?:don't (?!let me forget)|do not (?!let me forget)|never|if|explain|pretend|imagine|how (?:do|can)|what (?:is|does))\b", source):
        return False
    return bool(split_reminder_request(text) or re.match(
        r"^(?:(?:give|send|drop) me (?:a |another )?(?:reminder|nudge|ping|prod)|"
        r"(?:cancel|delete|remove|drop|dismiss|snooze|postpone|move|reschedule|change|push back)\b.*\breminder|"
        r"(?:make|change) (?:it|that)|(?:snooze|cancel|dismiss) (?:it|that)|(?:actually|i meant)\b)", source))
