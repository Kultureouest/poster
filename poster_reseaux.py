#!/usr/bin/env python3
"""
poster_reseaux.py — Publication réseaux Kulture Ouest (Instagram + Facebook)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Logique extraite À L'IDENTIQUE de publier_kulture_ouest.py (mêmes endpoints
v21.0, même modèle de conteneur Instagram, même retry 5x/30 s). Tourne aussi
bien en local que dans une GitHub Action.

Un "job" est un JSON minimal :
  {
    "title":            "Nom de l'évènement (pour les logs)",
    "image_url_social": "https://.../...-reseaux.jpg",
    "image_url":        "https://.../...-site.jpg",
    "jetpack_message":  "Légende + hashtags ...",
    "publish_at":       "2026-06-25T09:00:00+02:00"
  }
(publish_at n'est PAS utilisé ici : c'est run_file.py qui décide quand un job
est dû. Ce module se contente de poster.)

Secrets attendus dans l'environnement :
  IG_TOKEN, IG_BUSINESS_ID, FB_PAGE_TOKEN, FB_PAGE_ID

Usage :
  python3 poster_reseaux.py job.json            # poste pour de vrai
  python3 poster_reseaux.py job.json --dry-run  # vérifie tokens + image, ne poste rien
"""

import os
import sys
import json
import time
import requests

IG_API_URL = "https://graph.instagram.com/v21.0"
FB_API_URL = "https://graph.facebook.com/v21.0"


# ─── Publication Instagram (identique à publier_kulture_ouest.py) ──────────────

def publier_instagram(image_url, legende):
    print("\n┌─ INSTAGRAM ─────────────────────────────────────────────")

    if not image_url:
        print("│  ⚠️  Pas d'image_url fournie — publication Instagram ignorée")
        print("└─────────────────────────────────────────────────────────")
        return None

    ig_token       = os.environ.get("IG_TOKEN")
    ig_business_id = os.environ.get("IG_BUSINESS_ID")

    if not ig_token or not ig_business_id:
        print("│  ⚠️  IG_TOKEN / IG_BUSINESS_ID absents de l'environnement")
        print("└─────────────────────────────────────────────────────────")
        return None

    # Temps 1 — création du conteneur média
    r = requests.post(
        f"{IG_API_URL}/{ig_business_id}/media",
        data={"image_url": image_url, "caption": legende, "access_token": ig_token},
    )
    if r.status_code not in (200, 201):
        print(f"│  ❌ Conteneur non créé : {r.status_code} — {r.text[:300]}")
        print("└─────────────────────────────────────────────────────────")
        return None

    creation_id = r.json()["id"]
    print(f"│  ✅ Conteneur créé — ID {creation_id}")

    # Attente que le conteneur soit prêt (status_code = FINISHED)
    status = None
    for _ in range(10):
        r = requests.get(
            f"{IG_API_URL}/{creation_id}",
            params={"fields": "status_code", "access_token": ig_token},
        )
        status = r.json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            print("│  ❌ Conteneur en erreur lors du traitement")
            print("└─────────────────────────────────────────────────────────")
            return None
        time.sleep(2)
    if status != "FINISHED":
        print(f"│  ❌ Conteneur non prêt après 20 s (status : {status})")
        print("└─────────────────────────────────────────────────────────")
        return None

    # Temps 2 — publication du conteneur (réessai sur 5xx)
    last_err = ""
    for attempt in range(1, 6):
        r = requests.post(
            f"{IG_API_URL}/{ig_business_id}/media_publish",
            data={"creation_id": creation_id, "access_token": ig_token},
        )
        if r.status_code in (200, 201):
            media_id = r.json()["id"]
            print(f"│  ✅ Publié sur Instagram — ID média {media_id}")
            print("└─────────────────────────────────────────────────────────")
            return media_id
        last_err = f"{r.status_code} — {r.text[:200]}"
        if r.status_code < 500:
            break
        if attempt < 5:
            print(f"│  ⏳ Tentative {attempt}/5 échouée ({last_err}) — nouvel essai dans 30 s…")
            time.sleep(30)

    print(f"│  ❌ Publication échouée : {last_err}")
    print("└─────────────────────────────────────────────────────────")
    return None


# ─── Publication Facebook (identique à publier_kulture_ouest.py) ───────────────

def publier_facebook(image_url, legende):
    print("\n┌─ FACEBOOK ──────────────────────────────────────────────")

    if not image_url:
        print("│  ⚠️  Pas d'image_url fournie — publication Facebook ignorée")
        print("└─────────────────────────────────────────────────────────")
        return None

    fb_token   = os.environ.get("FB_PAGE_TOKEN")
    fb_page_id = os.environ.get("FB_PAGE_ID")

    if not fb_token or not fb_page_id:
        print("│  ⚠️  FB_PAGE_TOKEN / FB_PAGE_ID absents de l'environnement")
        print("└─────────────────────────────────────────────────────────")
        return None

    last_err = ""
    for attempt in range(1, 6):
        r = requests.post(
            f"{FB_API_URL}/{fb_page_id}/photos",
            data={"url": image_url, "caption": legende, "access_token": fb_token},
        )
        if r.status_code in (200, 201):
            data = r.json()
            post_id = data.get("post_id", data.get("id"))
            print(f"│  ✅ Publié sur Facebook — ID post {post_id}")
            print("└─────────────────────────────────────────────────────────")
            return post_id
        last_err = f"{r.status_code} — {r.text[:200]}"
        if r.status_code < 500:
            break
        if attempt < 5:
            print(f"│  ⏳ Tentative {attempt}/5 échouée ({last_err}) — nouvel essai dans 30 s…")
            time.sleep(30)

    print(f"│  ❌ Publication échouée : {last_err}")
    print("└─────────────────────────────────────────────────────────")
    return None


# ─── Vérification (dry-run) : tokens valides + image accessible, sans rien poster ─

def verifier(job):
    ok = True
    social_img = (job.get("image_url_social") or "").strip() or (job.get("image_url") or "").strip()
    print(f"  Image réseaux : {social_img or '(aucune)'}")
    if not social_img:
        print("  ❌ Aucune image_url_social / image_url")
        ok = False
    else:
        try:
            ri = requests.get(social_img, timeout=15)
            print(f"  Image accessible : HTTP {ri.status_code}")
            if ri.status_code != 200:
                ok = False
        except Exception as e:
            print(f"  ❌ Image inaccessible : {e}")
            ok = False

    ig_token = os.environ.get("IG_TOKEN"); ig_id = os.environ.get("IG_BUSINESS_ID")
    if ig_token and ig_id:
        r = requests.get(f"{IG_API_URL}/{ig_id}",
                         params={"fields": "id,username", "access_token": ig_token})
        print(f"  Token Instagram : HTTP {r.status_code} {'OK' if r.status_code == 200 else r.text[:150]}")
        if r.status_code != 200:
            ok = False
    else:
        print("  ❌ IG_TOKEN / IG_BUSINESS_ID absents"); ok = False

    fb_token = os.environ.get("FB_PAGE_TOKEN"); fb_id = os.environ.get("FB_PAGE_ID")
    if fb_token and fb_id:
        r = requests.get(f"{FB_API_URL}/{fb_id}",
                         params={"fields": "id,name", "access_token": fb_token})
        print(f"  Token Facebook  : HTTP {r.status_code} {'OK' if r.status_code == 200 else r.text[:150]}")
        if r.status_code != 200:
            ok = False
    else:
        print("  ❌ FB_PAGE_TOKEN / FB_PAGE_ID absents"); ok = False

    return ok


# ─── Poste un job (les 2 réseaux) ──────────────────────────────────────────────

def poster_job(job):
    social_img = (job.get("image_url_social") or "").strip() or (job.get("image_url") or "").strip()
    legende    = job.get("jetpack_message", "")
    ig = publier_instagram(social_img, legende)
    fb = publier_facebook(social_img, legende)
    return ig, fb


def main():
    args  = sys.argv[1:]
    dry   = "--dry-run" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        print("\nUsage : python3 poster_reseaux.py job.json [--dry-run]\n")
        sys.exit(1)

    with open(files[0], "r", encoding="utf-8") as f:
        job = json.load(f)

    print("\n" + "═" * 58)
    print(f"  POSTER RÉSEAUX — {job.get('title', '(sans titre)')}")
    print("═" * 58)

    if dry:
        print("\n  [DRY-RUN] aucune publication, vérification seulement :")
        ok = verifier(job)
        print("\n  " + ("✅ Prêt à publier." if ok else "❌ Problème détecté (voir ci-dessus)."))
        sys.exit(0 if ok else 2)

    ig, fb = poster_job(job)
    print("\n" + "═" * 58)
    print(f"  Instagram : {'✅ ' + str(ig) if ig else '❌ non publié'}")
    print(f"  Facebook  : {'✅ ' + str(fb) if fb else '❌ non publié'}")
    print("═" * 58 + "\n")
    sys.exit(0 if (ig and fb) else 1)


if __name__ == "__main__":
    main()
