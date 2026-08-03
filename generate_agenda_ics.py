#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genere agenda-reseaux.ics a partir des jobs en attente (file/*.json)
et des jobs deja publies (done/*.json). Stdlib seule."""
import glob, json, datetime, hashlib

# Historique des posts publies conserve dans le calendrier, en jours.
# Au-dela, ils ne sont plus ecrits : evite un fichier qui grossit sans fin.
JOURS_HISTORIQUE = 90


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


def lire(motif):
    """Charge les jobs valides d un dossier."""
    out = []
    for p in sorted(glob.glob(motif)):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if d.get("publish_at") and d.get("title"):
            out.append(d)
    return out


def cle(d):
    """UID stable : identique avant et apres publication, pour que le
    calendrier mette a jour l evenement au lieu d en creer un second."""
    return hashlib.md5((d["title"] + d["publish_at"]).encode()).hexdigest() + "@poster.kultureouest.fr"


def main():
    limite = datetime.datetime.now() - datetime.timedelta(days=JOURS_HISTORIQUE)
    par_uid = {}

    # 1) Jobs deja publies (done/) -> marques "Publie"
    for d in lire("done/*.json"):
        try:
            dt = datetime.datetime.fromisoformat(d["publish_at"])
        except Exception:
            continue
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        if dt < limite:
            continue
        d["_publie"] = True
        par_uid[cle(d)] = d

    # 2) Jobs en attente (file/) -> marques "Post reseaux".
    #    Si un job est deja connu comme publie, la version publiee gagne.
    for d in lire("file/*.json"):
        uid = cle(d)
        if uid in par_uid:
            continue
        d["_publie"] = False
        par_uid[uid] = d

    jobs = sorted(par_uid.items(), key=lambda kv: kv[1]["publish_at"])

    ve = []
    for uid, d in jobs:
        start = datetime.datetime.fromisoformat(d["publish_at"])
        end = start + datetime.timedelta(minutes=30)
        stamp = start.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        first = (d.get("jetpack_message", "").split("\n", 1)[0])[:120]
        prefixe = "\u2705 Publi\u00e9 : " if d["_publie"] else "\U0001F4E3 Post r\u00e9seaux : "
        ve.append("\r\n".join([
            "BEGIN:VEVENT",
            "UID:" + uid,
            "DTSTAMP:" + stamp,
            "DTSTART;TZID=Europe/Paris:" + start.strftime("%Y%m%dT%H%M%S"),
            "DTEND;TZID=Europe/Paris:" + end.strftime("%Y%m%dT%H%M%S"),
            "SUMMARY:" + prefixe + esc(d["title"]),
            "DESCRIPTION:" + esc(first),
            "END:VEVENT",
        ]))

    cal = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//Kulture Ouest//Posts reseaux//FR", "CALSCALE:GREGORIAN",
           "METHOD:PUBLISH", "X-WR-CALNAME:Kulture Ouest \u2014 Posts r\u00e9seaux",
           VTIMEZONE] + ve + ["END:VCALENDAR"]
    with open("agenda-reseaux.ics", "w", encoding="utf-8") as f:
        f.write("\r\n".join(cal) + "\r\n")

    nb_pub = sum(1 for _, d in jobs if d["_publie"])
    print(str(len(ve)) + " post(s) ecrits (" + str(nb_pub) + " publie(s), " + str(len(ve) - nb_pub) + " en attente)")


if __name__ == "__main__":
    main()
