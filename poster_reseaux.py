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


# ─── Publication Facebook (inchangée) ─────────────────────────────────────────

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


# ─── Bluesky / AT Protocol (best effort) ──────────────────────────────────────

def _bsky_resolve_did(handle):
    """handle -> DID (s'appuie sur le TXT _atproto du domaine)."""
    r = requests.get(
        f"{BSKY_ENTRY}/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle}, timeout=20,
    )
    r.raise_for_status()
    return r.json()["did"]


def _bsky_resolve_pds(did):
    """DID -> URL du PDS hôte (via l'annuaire PLC), pour viser le bon serveur."""
    r = requests.get(f"https://plc.directory/{did}", timeout=20)
    r.raise_for_status()
    for s in r.json().get("service", []):
        if s.get("type") == "AtprotoPersonalDataServer":
            return s["serviceEndpoint"].rstrip("/")
    return BSKY_ENTRY


def _bsky_caption(jetpack_message):
    """
    Dérive une légende Bluesky (≤ 300 graphèmes) à partir du jetpack_message :
    accroche + factuel (2 premiers paragraphes), hashtags réduits à 1-2 clés
    + #kultureouest17. Les hashtags génériques CharenteMaritime sont retirés.
    """
    txt = jetpack_message or ""
    tags = re.findall(r"#\w+", txt)
    body = re.sub(r"#\w+", "", txt)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    paras = [p.strip() for p in body.split("\n") if p.strip()]
    accroche = " ".join(paras[:2]) if paras else body
    accroche = re.sub(r"\s+", " ", accroche).strip()

    generiques = {"#charentemaritime", "#sortirencharentemaritime", "#kultureouest17"}
    key = []
    for t in tags:
        if t.lower() in generiques:
            continue
        if t not in key:
            key.append(t)
        if len(key) == 2:
            break
    key.append("#kultureouest17")
    suffix = " " + " ".join(key)

    budget = BSKY_MAX_GRAPHEMES - len(suffix) - 1
    if len(accroche) > budget:
        accroche = accroche[:budget - 1].rstrip(" .,;:!?-") + "…"
    return (accroche + suffix).strip()


def _bsky_facets(text):
    """Rend les #hashtags cliquables (facets sur offsets d'OCTETS UTF-8)."""
    facets = []
    for m in re.finditer(r"#(\w+)", text):
        start = len(text[:m.start()].encode("utf-8"))
        end   = len(text[:m.end()].encode("utf-8"))
        facets.append({
            "index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}],
        })
    return facets


def _bsky_prepare_image(image_url):
    """Télécharge l'image ; recompresse en JPEG si elle dépasse la limite de blob."""
    r = requests.get(image_url, timeout=30)
    r.raise_for_status()
    data = r.content
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    if len(data) <= BSKY_BLOB_MAX:
        return data, mime
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        for q in (85, 75, 65, 55):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            if buf.tell() <= BSKY_BLOB_MAX:
                return buf.getvalue(), "image/jpeg"
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"│  ⚠️  Recompression impossible ({e}) — image de {len(data)} o envoyée telle quelle")
        return data, mime


def publier_bluesky(image_url, jetpack_message, title):
    print("\n┌─ BLUESKY ───────────────────────────────────────────────")
    handle = os.environ.get("BSKY_HANDLE")
    app_pw = os.environ.get("BSKY_APP_PASSWORD")

    if not handle or not app_pw:
        print("│  ⚠️  BSKY_HANDLE / BSKY_APP_PASSWORD absents — Bluesky ignoré")
        print("└─────────────────────────────────────────────────────────")
        return None
    if not image_url:
        print("│  ⚠️  Pas d'image — Bluesky ignoré")
        print("└─────────────────────────────────────────────────────────")
        return None

    try:
        did = _bsky_resolve_did(handle)
        pds = _bsky_resolve_pds(did)

        s = requests.post(
            f"{pds}/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": app_pw}, timeout=20,
        )
        if s.status_code != 200:
            print(f"│  ❌ Auth échouée : {s.status_code} — {s.text[:200]}")
            print("└─────────────────────────────────────────────────────────")
            return None
        sess = s.json()
        jwt = sess["accessJwt"]
        did = sess.get("did", did)
        auth = {"Authorization": f"Bearer {jwt}"}

        img_bytes, mime = _bsky_prepare_image(image_url)
        ub = requests.post(
            f"{pds}/xrpc/com.atproto.repo.uploadBlob",
            headers={**auth, "Content-Type": mime},
            data=img_bytes, timeout=60,
        )
        if ub.status_code != 200:
            print(f"│  ❌ uploadBlob échoué : {ub.status_code} — {ub.text[:200]}")
            print("└─────────────────────────────────────────────────────────")
            return None
        blob = ub.json()["blob"]

        caption = _bsky_caption(jetpack_message)
        record = {
            "$type": "app.bsky.feed.post",
            "text": caption,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "langs": ["fr"],
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [{"alt": (title or caption)[:280], "image": blob}],
            },
        }
        facets = _bsky_facets(caption)
        if facets:
            record["facets"] = facets

        cr = requests.post(
            f"{pds}/xrpc/com.atproto.repo.createRecord",
            headers=auth,
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
            timeout=30,
        )
        if cr.status_code not in (200, 201):
            print(f"│  ❌ createRecord échoué : {cr.status_code} — {cr.text[:200]}")
            print("└─────────────────────────────────────────────────────────")
            return None

        uri = cr.json().get("uri", "")
        print(f"│  ✅ Publié sur Bluesky — {uri}")
        print("└─────────────────────────────────────────────────────────")
        return uri

    except Exception as e:
        print(f"│  ❌ Bluesky exception : {e}")
        print("└─────────────────────────────────────────────────────────")
        return None


# ─── Vérification (dry-run) : tokens + image, sans rien poster ─────────────────

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

    # Bluesky = best effort : vérifié mais n'affecte pas le verdict "ok"
    bsky_h = os.environ.get("BSKY_HANDLE"); bsky_p = os.environ.get("BSKY_APP_PASSWORD")
    if bsky_h and bsky_p:
        try:
            did = _bsky_resolve_did(bsky_h)
            pds = _bsky_resolve_pds(did)
            r = requests.post(f"{pds}/xrpc/com.atproto.server.createSession",
                              json={"identifier": bsky_h, "password": bsky_p}, timeout=20)
            print(f"  Token Bluesky   : HTTP {r.status_code} {'OK' if r.status_code == 200 else r.text[:150]}  (best effort)")
        except Exception as e:
            print(f"  ⚠️  Bluesky non vérifié : {e}  (best effort)")
    else:
        print("  ⚠️  BSKY_HANDLE / BSKY_APP_PASSWORD absents  (best effort)")

    return ok


# ─── Poste un job (les 3 réseaux) ─────────────────────────────────────────────

def poster_job(job):
    """
    Poste sur IG, FB puis Bluesky. Renvoie (ig, fb, bsky).
    Bluesky est best effort : run_file.py ne se base QUE sur (ig, fb) pour
    décider done/ vs failed/ — un échec Bluesky ne provoque jamais de repost.
    """
    social_img = (job.get("image_url_social") or "").strip() or (job.get("image_url") or "").strip()
    legende    = job.get("jetpack_message", "")
    title      = job.get("title", "")
    ig   = publier_instagram(social_img, legende)
    fb   = publier_facebook(social_img, legende)
    bsky = publier_bluesky(social_img, legende, title)
    return ig, fb, bsky


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

    ig, fb, bsky = poster_job(job)
    print("\n" + "═" * 58)
    print(f"  Instagram : {'✅ ' + str(ig) if ig else '❌ non publié'}")
    print(f"  Facebook  : {'✅ ' + str(fb) if fb else '❌ non publié'}")
    print(f"  Bluesky   : {'✅ ' + str(bsky) if bsky else '⚠️ non publié (best effort)'}")
    print("═" * 58 + "\n")
    # Verdict basé sur IG + FB uniquement (Bluesky best effort)
    sys.exit(0 if (ig and fb) else 1)


if __name__ == "__main__":
    main()
