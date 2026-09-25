#!/usr/bin/env python3
"""
run_file.py — Le "facteur" Kulture Ouest
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Parcourt file/*.json. Pour chaque job dont publish_at est arrivé (<= maintenant,
comparé en UTC), appelle poster_reseaux.poster_job(), puis range le job :
  • succès Instagram ET Facebook -> done/
  • échec IG ou FB               -> failed/  (+ code de sortie 1 = alerte)
Les jobs encore dans le futur sont laissés en place pour un prochain tour.

Garde-fou (incident du 25/09/2026) : un job en retard de plus de RETARD_MAX
(2 h) n'est PAS publié. Il part dans failed/ avec le préfixe "perime_" et le run
échoue (alerte). Cas typique : année mal saisie dans le Builder (2025 au lieu
de 2026). Un retard normal (ping manqué, file GitHub) reste bien sous 2 h.
Pour le relancer : corriger publish_at et remettre le fichier dans file/.

Bluesky est BEST EFFORT : son résultat est loggé mais n'entre PAS dans la
décision done/failed. Ainsi, un échec Bluesky isolé ne renvoie jamais le job
en failed/ (ce qui provoquerait un repost IG/FB en double au tour suivant).

publish_at accepté : ISO 8601, idéalement avec fuseau, ex. "2026-06-25T09:00:00+02:00".
Si aucun fuseau n'est précisé, on suppose l'heure de Paris.
"""

import os
import sys
import json
import glob
import shutil
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:
    PARIS = None

import poster_reseaux

BASE       = os.path.dirname(os.path.abspath(__file__))
FILE_DIR   = os.path.join(BASE, "file")
DONE_DIR   = os.path.join(BASE, "done")
FAILED_DIR = os.path.join(BASE, "failed")

RETARD_MAX = timedelta(hours=2)


def parse_when(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PARIS or timezone.utc)
    return dt


def main():
    os.makedirs(FILE_DIR, exist_ok=True)
    os.makedirs(DONE_DIR, exist_ok=True)
    os.makedirs(FAILED_DIR, exist_ok=True)

    now  = datetime.now(timezone.utc)
    jobs = sorted(glob.glob(os.path.join(FILE_DIR, "*.json")))
    if not jobs:
        print("Aucun job en attente.")
        return 0

    any_fail = False
    posted   = 0

    for path in jobs:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            job = json.load(f)

        when_s = job.get("publish_at")
        try:
            when_dt = parse_when(when_s) if when_s else None
        except Exception as e:
            print(f"⚠️  publish_at illisible dans {name} ({e}) — ignoré ce tour")
            continue
        due = (when_dt <= now) if when_dt else True

        if when_dt and now - when_dt > RETARD_MAX:
            ts = now.strftime("%Y%m%d-%H%M%S")
            shutil.move(path, os.path.join(FAILED_DIR, f"{ts}_perime_{name}"))
            print(f"🛑 {name} : publish_at={when_s} déjà dépassé de plus de 2 h, "
                  f"NON publié (date probablement erronée) — déplacé dans failed/")
            any_fail = True
            continue

        if not due:
            print(f"… {name} : pas encore l'heure (publish_at={when_s})")
            continue

        print(f"\n>>> Job dû : {name} (publish_at={when_s})")
        ig, fb, bsky = poster_reseaux.poster_job(job)
        ts = now.strftime("%Y%m%d-%H%M%S")

        # Verdict done/failed sur IG + FB uniquement. Bluesky = best effort.
        if ig and fb:
            shutil.move(path, os.path.join(DONE_DIR, f"{ts}_{name}"))
            bsky_txt = str(bsky) if bsky else "échec/désactivé (best effort)"
            print(f"✅ Posté (IG={ig}, FB={fb}, Bluesky={bsky_txt}) — archivé dans done/")
            posted += 1
        else:
            shutil.move(path, os.path.join(FAILED_DIR, f"{ts}_{name}"))
            print(f"❌ Échec (IG={ig}, FB={fb}, Bluesky={bsky}) — déplacé dans failed/")
            any_fail = True

    print(f"\nBilan : {posted} job(s) posté(s).")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
