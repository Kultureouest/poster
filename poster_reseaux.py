#!/usr/bin/env python3
"""
poster_reseaux.py — Publication réseaux Kulture Ouest (Instagram + Facebook + Bluesky)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Instagram + Facebook : logique inchangée (Graph API v21.0, conteneur IG, retry 5x/30 s).
Bluesky : ajouté en « best effort » — posté après IG/FB, son échec est loggé mais
NE renvoie PAS le job en failed/ (voir run_file.py) → jamais de double post IG/FB.

Un "job" est un JSON minimal :
  {
    "title":            "Nom de l'évènement (pour les logs + alt Bluesky)",
    "image_url_social": "https://.../...-reseaux.jpg",
    "image_url":        "https://.../...-site.jpg",
    "jetpack_message":  "Légende + hashtags ...",
    "publish_at":       "2026-06-25T09:00:00+02:00"
  }

Secrets attendus dans l'environnement :
  IG_TOKEN, IG_BUSINESS_ID, FB_PAGE_TOKEN, FB_PAGE_ID
  BSKY_HANDLE, BSKY_APP_PASSWORD   (Bluesky — best effort, ignoré si absents)

Usage :
  python3 poster_reseaux.py job.json            # poste pour de vrai
  python3 poster_reseaux.py job.json --dry-run  # vérifie tokens + image, ne poste rien
"""

import os
import sys
import io
import re
import json
import time
from datetime import datetime, timezone

import requests

IG_API_URL = "https://graph.instagram.com/v21.0"
FB_API_URL = "https://graph.facebook.com/v21.0"

BSKY_ENTRY         = "https://bsky.social"   # point d'entrée pour resolveHandle
BSKY_MAX_GRAPHEMES = 300                     # limite dure d'un post Bluesky
BSKY_BLOB_MAX      = 976_000                 # ~976 Ko : taille max d'un blob image
BSKY_LINK_LABEL    = "kultureouest.fr"       # libellé cliquable affiché pour le lien article


# ─── Publication Instagram (inchangée) ────────────────────────────────────────

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

    # Temps 2 — publication du conteneur
    # Réessai sur 5xx, ET sur l'erreur 9007 / sous-code 2207027 ("Media ID is
    # not available" / "The media is not ready to be published"). Ce cas est
    # documenté comme récurrent côté Graph API même après un status_code
    # FINISHED confirmé ci-dessus : Meta la marque is_transient=false, mais
    # dans la pratique un nouvel essai quelques secondes plus tard passe
    # presque toujours. Sans ce réessai ciblé, IG échoue alors que FB/Bluesky
    # ont déjà été publiés pour le même job, qui part directement en failed/.
    last_err = ""
    for attempt in range(1, 6):
        r = requests.post(
            f"{IG_API_URL}/{ig_business_id}/media_publish",
            data={"creation_id": creation_id, "access_token": ig_token},
        )
        if r.status_code in
