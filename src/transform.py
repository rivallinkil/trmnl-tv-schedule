"""
Picks, for each chosen channel, what to show: the programme on now and the next one, or tonight's two parts.

Input: one relay file (relay/build.py) per chosen channel, {id, name, generated, programmes: [[start, stop, title,
category], ...]}. TRMNL wraps several polling URLs as {IDX_0: first channel, IDX_1: ...}; a single URL arrives
unwrapped. Plus the trmnl namespace with the custom field "mode".
Output: {mode: "now" | "tonight", heading, updated, rows: [{name, a: slot, b: slot}]}, where a slot is
{start, end, title, category, progress} (times as "21:10", progress in % for a programme on now, else None).
"""
import time
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # no tz database: fall back to the account's offset below
    PARIS = None

# Auto mode shows tonight's programmes from EVENING_FROM until EVENING_UNTIL (local hours), now/next otherwise.
EVENING_FROM = 18
EVENING_UNTIL = 22
# Tonight's first part starts in this window (minutes after midnight) and lasts at least MIN_MINUTES:
# weather, lottery draws and short magazines around 21:00 are skipped.
PRIME_FROM = 20 * 60 + 45
PRIME_UNTIL = 22 * 60
MIN_MINUTES = 40
# The second part starts before midnight and is not the night filler.
SECOND_UNTIL = 24 * 60
NIGHT_FILLER = "Programme indéterminé"
# "Next" skips anything shorter (trailers, weather, lottery draws).
NEXT_MIN_MINUTES = 10
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


def local_zone(trmnl):
    if PARIS:
        return PARIS
    offset = (trmnl.get("user") or {}).get("utc_offset") or 3600
    return timezone(timedelta(seconds=int(offset)))


def channel_files(input):
    """The polled channel files in the order of the polling URLs; failed requests are left out."""
    if "IDX_0" in input:
        keys = sorted((k for k in input if k.startswith("IDX_")), key=lambda k: int(k[4:]))
        files = [input[k] for k in keys]
    else:
        files = [input]
    return [f for f in files if isinstance(f, dict) and isinstance(f.get("programmes"), list)]


def merged(rows):
    """Consecutive parts with the same title (episodes of a series, a film split by ads) become one."""
    out = []
    for start, stop, title, category in rows:
        if out and out[-1][2] == title and out[-1][1] == start:
            out[-1][1] = stop
        else:
            out.append([start, stop, title, category])
    return out


def slot(row, tz, now=None):
    if not row:
        return None
    start, stop, title, category = row
    progress = None
    if now is not None and start <= now < stop:
        progress = round(100 * (now - start) / (stop - start))
    return {
        "start": datetime.fromtimestamp(start, tz).strftime("%H:%M"),
        "end": datetime.fromtimestamp(stop, tz).strftime("%H:%M"),
        "title": title,
        "category": category,
        "progress": progress,
    }


def now_next(rows, now):
    for i, row in enumerate(rows):
        if row[0] <= now < row[1]:
            return row, rows[i + 1] if i + 1 < len(rows) else None
    upcoming = [r for r in rows if r[0] > now]
    return None, upcoming[0] if upcoming else None


def skip_short(rows, row):
    """The first programme from `row` on lasting NEXT_MIN_MINUTES or more."""
    if not row:
        return None
    later = [r for r in rows[rows.index(row):] if r[1] - r[0] >= NEXT_MIN_MINUTES * 60]
    return later[0] if later else row


def tonight(rows, day, tz):
    """First and second part of the evening of `day` (a local date)."""
    midnight = datetime(day.year, day.month, day.day, tzinfo=tz).timestamp()

    def minutes(ts):
        return (ts - midnight) / 60

    long = [r for r in rows if r[1] - r[0] >= MIN_MINUTES * 60]
    prime = next((r for r in long if PRIME_FROM <= minutes(r[0]) < PRIME_UNTIL), None)
    if not prime:
        # Nothing long starts around 21:00: whatever is on at 21:15.
        prime = next((r for r in rows if r[0] <= midnight + 21.25 * 3600 < r[1]), None)
    if not prime:
        return None, None
    second = next((r for r in long if r[0] >= prime[1] and minutes(r[0]) < SECOND_UNTIL
                   and r[3] != NIGHT_FILLER), None)
    return prime, second


def run(input):
    trmnl = input.get("trmnl") or {}
    fields = (trmnl.get("plugin_settings") or {}).get("custom_fields_values") or {}
    tz = local_zone(trmnl)
    now = int(time.time())
    local = datetime.fromtimestamp(now, tz)

    mode = (fields.get("mode") or "auto").lower()
    if mode not in ("now", "tonight"):
        mode = "tonight" if EVENING_FROM <= local.hour < EVENING_UNTIL else "now"
    day = local.date()
    if mode == "tonight" and local.hour < 4:
        day -= timedelta(days=1)  # just after midnight, tonight is still yesterday's evening

    rows = []
    for channel in channel_files(input):
        if not channel["programmes"]:
            continue
        progs = merged(channel["programmes"])
        if mode == "tonight":
            a, b = tonight(progs, day, tz)
        else:
            a, b = now_next(progs, now)
            b = skip_short(progs, b)
        if a or b:
            rows.append({"name": channel.get("name") or channel.get("id"), "a": slot(a, tz, now), "b": slot(b, tz, now)})

    if mode == "tonight":
        heading = "Ce soir"
    else:
        heading = "En ce moment"
    return {
        "mode": mode,
        "heading": heading,
        "date": f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}",
        "updated": local.strftime("%H:%M"),
        "rows": rows,
    }
