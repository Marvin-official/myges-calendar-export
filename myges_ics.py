#!/usr/bin/env python3
"""Fetch the MyGES agenda and write it as an iCalendar (.ics) file.

Uses the same Kordis API as the official MyGES mobile app, so no HTML
scraping is needed. Standard library only.

Credentials come from the MYGES_USERNAME and MYGES_PASSWORD environment
variables.
"""

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AUTH_URL = "https://authentication.kordis.fr/oauth/authorize?response_type=token&client_id=skolae-app"
API_URL = "https://api.kordis.fr"
USER_AGENT = "myges-ics/1.0"
CHUNK_DAYS = 14


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get_token(username, password):
    """Log in and return a bearer token.

    The auth server answers with a redirect to
    comreseaugesapp://oauth2redirect#access_token=...; we read the token
    from that Location header instead of following it.
    """
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(
        AUTH_URL, headers={"Authorization": f"Basic {creds}", "User-Agent": USER_AGENT}
    )
    try:
        urllib.request.build_opener(_NoRedirect).open(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("Login failed: wrong MyGES username or password")
        if e.code in (301, 302, 303, 307, 308):
            fragment = urllib.parse.urlparse(e.headers.get("Location", "")).fragment
            token = urllib.parse.parse_qs(fragment).get("access_token")
            if token:
                return token[0]
        sys.exit(f"Login failed: HTTP {e.code}")
    sys.exit("Login failed: no access token in the response")


def _ms(dt):
    return int(dt.timestamp() * 1000)


def fetch_agenda(token, start, end):
    """Return all agenda entries between start and end, fetched in chunks."""
    entries = {}
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        query = urllib.parse.urlencode({"start": _ms(cursor), "end": _ms(chunk_end)})
        req = urllib.request.Request(
            f"{API_URL}/me/agenda?{query}",
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            sys.exit(f"Agenda request failed: HTTP {e.code}")
        for entry in data.get("result") or []:
            key = entry.get("reservation_id") or (entry.get("start_date"), entry.get("name"))
            entries[key] = entry
        cursor = chunk_end
    return sorted(entries.values(), key=lambda e: e.get("start_date") or 0)


def _escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line):
    """Fold a content line to 75 octets, as RFC 5545 requires."""
    parts, current = [], ""
    for ch in line:
        limit = 75 if not parts else 74  # continuation lines start with a space
        if len((current + ch).encode()) > limit:
            parts.append(current)
            current = ch
        else:
            current += ch
    parts.append(current)
    return "\r\n ".join(parts)


def _ics_time(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _vevent(entry, stamp):
    discipline = entry.get("discipline") or {}
    title = entry.get("name") or discipline.get("name") or "Cours"
    kind = entry.get("type") or ""
    modality = entry.get("modality") or ""
    teacher = entry.get("teacher") or discipline.get("teacher") or ""

    # The title is the topic; exams and other non-class types get a short prefix.
    summary = title
    if kind and kind.lower() != "cours" and kind.lower() not in title.lower():
        summary = f"{kind} · {summary}"

    # Location reads "Room — Campus", so both show under the title on the phone.
    rooms, campuses = [], []
    for room in entry.get("rooms") or []:
        if room.get("name") and room["name"] not in rooms:
            rooms.append(room["name"])
        if room.get("campus") and room["campus"] not in campuses:
            campuses.append(room["campus"])
    if not rooms and modality.lower() == "distanciel":
        rooms.append("Distanciel")
    location = " — ".join(p for p in (", ".join(rooms), ", ".join(campuses)) if p)

    details = [
        ("Intervenant", teacher),
        ("Type", kind),
        ("Modalité", modality),
        ("Commentaire", entry.get("comment") or ""),
    ]
    description = "\n".join(f"{label} : {value}" for label, value in details if value)

    uid = entry.get("reservation_id")
    if not uid:
        uid = hashlib.sha1(f"{entry.get('start_date')}{title}".encode()).hexdigest()

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@myges",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{_ics_time(entry['start_date'])}",
        f"DTEND:{_ics_time(entry.get('end_date') or entry['start_date'])}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if str(entry.get("state") or "").lower() in ("cancelled", "canceled", "annulé", "annule"):
        lines.append("STATUS:CANCELLED")
    lines.append("END:VEVENT")
    return lines


def build_ics(entries, calendar_name):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//myges-ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        "X-WR-TIMEZONE:Europe/Paris",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for entry in entries:
        if entry.get("start_date"):
            lines.extend(_vevent(entry, stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="myges.ics", help="output .ics path")
    parser.add_argument("--weeks-back", type=int, default=4, help="past weeks to include")
    parser.add_argument("--weeks-ahead", type=int, default=20, help="future weeks to include")
    parser.add_argument("--name", default="MyGES", help="calendar name shown on the phone")
    args = parser.parse_args()

    username = os.environ.get("MYGES_USERNAME")
    password = os.environ.get("MYGES_PASSWORD")
    if not username or not password:
        sys.exit("Set MYGES_USERNAME and MYGES_PASSWORD")

    now = datetime.now(timezone.utc)
    token = get_token(username, password)
    entries = fetch_agenda(
        token, now - timedelta(weeks=args.weeks_back), now + timedelta(weeks=args.weeks_ahead)
    )

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(entries, args.name))
    print(f"Wrote {len(entries)} events")


if __name__ == "__main__":
    main()
