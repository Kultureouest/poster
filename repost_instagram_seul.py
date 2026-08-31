#!/usr/bin/env python3
"""
repost_instagram_seul.py — Republie UNIQUEMENT sur Instagram un job resté dans failed/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

À utiliser quand un job de failed/ a échoué uniquement côté Instagram alors que
Facebook et/ou Bluesky ont déjà été publiés pour ce même job. On ne repasse
surtout pas par poster_reseaux.poster_job() ni par run_file.py : ça republierait
Facebook et Bluesky en double. Ce script n'appelle que publier_instagram().

À placer à la racine du repo (à côté de poster_reseaux.py, run_file.py), car il
importe poster_reseaux.

Usage :
  python3 repost_instagram_seul.py failed/<nom-du-fichier>.json
  python3 repost_instagram_seul.py failed/<nom-du-fichier>.json --dry-run
  python3 repost_instagram_seul.py failed/<nom-du-fichier>.json --yes   # sans confirmation (CI)

Secrets attendus dans l'environnement (les mêmes que poster.yml) :
  IG_TOKEN, IG_BUSINESS_ID

En cas de succès : le fichier est déplacé vers done/ (préfixé "repost-ig_" pour
qu'on distingue dans l'historique une republication manuelle d'un post normal).
En cas d'échec : le fichier reste dans failed/, rien n'est déplacé.
"""

import os
import sys
import json
import shutil
from datetime import datetime, timezone

import poster_reseaux

BASE     = os.path.dirname(os.path.abspath(__file__))
DONE_DIR = os.path.join(BASE, "done")


def main():
    args  = sys.argv[1:]
    dry   = "--dry-run" in args
    force = "--yes" in args or "-y" in args
    files = [a for a in args if not a.startswith("-")]

    if not files:
        print("\nUsage : python3 repost_instagram_seul.py failed/<job>.json [--dry-run]\n")
        sys.exit(1)

    path = files[0]
    if not os.path.isfile(path):
        print(f"❌ Fichier introuvable : {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        job = json.load(f)

    social_img = (job.get("image_url_social") or "").strip() or (job.get("image_url") or "").strip()
    legende    = job.get("jetpack_message", "")
    title      = job.get("title", "(sans titre)")

    print("\n" + "═" * 58)
    print("  REPOST INSTAGRAM SEUL")
    print("═" * 58)
    print(f"  Titre   : {title}")
    print(f"  Fichier : {path}")
    print(f"  Image   : {social_img or '(aucune)'}")

    if dry:
        print("\n  [DRY-RUN] aucune publication effectuée.")
        print("  Pour vérifier tokens/image sans poster, utilise :")
        print("  python3 poster_reseaux.py " + path + " --dry-run")
        print("═" * 58 + "\n")
        sys.exit(0)

    if force:
        print("\n  ⚠️  Publication sur INSTAGRAM SEULEMENT (pas Facebook/Bluesky) — confirmée via --yes.")
    else:
        reponse = input(
            "\n  ⚠️  Ceci va publier sur INSTAGRAM SEULEMENT (pas Facebook/Bluesky).\n"
            "  Confirmer la publication ? (oui/non) : "
        ).strip().lower()
        if reponse not in ("oui", "o", "yes", "y"):
            print("  Annulé — rien n'a été publié ni déplacé.")
            sys.exit(0)

    ig = poster_reseaux.publier_instagram(social_img, legende)

    print("\n" + "═" * 58)
    if ig:
        print(f"  Instagram : ✅ publié — ID média {ig}")
        os.makedirs(DONE_DIR, exist_ok=True)
        ts   = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        name = os.path.basename(path)
        dest = os.path.join(DONE_DIR, f"{ts}_repost-ig_{name}")
        shutil.move(path, dest)
        print(f"  Déplacé vers : {dest}")
        print("═" * 58 + "\n")
        sys.exit(0)
    else:
        print("  Instagram : ❌ toujours en échec — voir le détail ci-dessus.")
        print(f"  Le fichier reste dans failed/ : {path}")
        print("═" * 58 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
