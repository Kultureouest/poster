#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genere agenda-reseaux.ics a partir des jobs en attente (file/*.json). Stdlib seule."""
import glob, json, datetime, hashlib

def esc(s):
    if s is None:
        return ""
    return (str(s).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Paris
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""

def main():
    jobs = []
    for p in sorted(glob.glob("file/*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if d.get("publish_at") and d.get("title"):
            jobs.append(d)
    jobs.sort(key=lambda d: d["publish_at"])

    ve = []
    for d in jobs:
        start = datetime.datetime.fromisoformat(d["publish_at"])
        end = start + datetime.timedelta(minutes=30)
        stamp = start.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uid = hashlib.md5((d["title"] + d["publish_at"]).encode()).hexdigest() + "@poster.kultureouest.fr"
        first = (d.get("jetpack_message", "").split("\n", 1)[0])[:120]
        ve.append("\r\n".join([
            "BEGIN:VEVENT",
            "UID:" + uid,
            "DTSTAMP:" + stamp,
            "DTSTART;TZID=Europe/Paris:" + start.strftime("%Y%m%dT%H%M%S"),
            "DTEND;TZID=Europe/Paris:" + end.strftime("%Y%m%dT%H%M%S"),
            "SUMMARY:\U0001F4E3 Post r\u00e9seaux : " + esc(d["title"]),
            "DESCRIPTION:" + esc(first),
            "END:VEVENT",
        ]))

    cal = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//Kulture Ouest//Posts reseaux//FR", "CALSCALE:GREGORIAN",
           "METHOD:PUBLISH", "X-WR-CALNAME:Kulture Ouest \u2014 Posts r\u00e9seaux",
           VTIMEZONE] + ve + ["END:VCALENDAR"]
    with open("agenda-reseaux.ics", "w", encoding="utf-8") as f:
        f.write("\r\n".join(cal) + "\r\n")
    print(str(len(ve)) + " post(s) ecrits dans agenda-reseaux.ics")

if __name__ == "__main__":
    main()
