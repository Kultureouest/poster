#!/usr/bin/env python3
"""
refresh_token.py — Rafraichit le token Instagram (cloud) et met a jour le secret GitHub IG_TOKEN.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tourne dans GitHub Actions (mensuel). Etapes :
  1. Rafraichit IG_TOKEN via graph.instagram.com/refresh_access_token (nouveau token, +60 j).
  2. Recupere la cle publique du depot.
  3. Chiffre le nouveau token (sealed box libsodium / PyNaCl).
  4. Reecrit le secret IG_TOKEN du depot via l'API GitHub.

Le rafraichissement N'INVALIDE PAS le token precedent (il l'etend) : la copie
locale du .env sur le Mac reste valable de son cote.

Env attendu :
  IG_TOKEN          — token Instagram actuel (secret du depot)
  GH_SECRETS_PAT    — PAT fine-grained (depot poster, permission Secrets: write)
  GITHUB_REPOSITORY — fourni automatiquement par GitHub Actions (owner/repo)
"""

import os
import sys
import json
import base64
import requests
from nacl import encoding, public

API = "https://api.github.com"


def main():
    ig_token = os.environ.get("IG_TOKEN")
    pat      = os.environ.get("GH_SECRETS_PAT")
    repo     = os.environ.get("GITHUB_REPOSITORY")  # ex : Kultureouest/poster

    if not (ig_token and pat and repo):
        print("❌ IG_TOKEN / GH_SECRETS_PAT / GITHUB_REPOSITORY manquant")
        sys.exit(1)

    # 1) Rafraichir le token Instagram
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": ig_token},
    )
    if r.status_code != 200:
        print(f"❌ Refresh Instagram echoue : {r.status_code} — {r.text[:300]}")
        sys.exit(1)
    data = r.json()
    new_token  = data["access_token"]
    expires_in = data.get("expires_in")
    jours = round(expires_in / 86400) if expires_in else "?"
    print(f"✅ Token Instagram rafraichi (valide ~{jours} j).")

    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 2) Cle publique du depot
    rk = requests.get(f"{API}/repos/{repo}/actions/secrets/public-key", headers=headers)
    if rk.status_code != 200:
        print(f"❌ Cle publique non recuperee : {rk.status_code} — {rk.text[:300]}")
        sys.exit(1)
    key_id = rk.json()["key_id"]
    pub_b64 = rk.json()["key"]

    # 3) Chiffrer le nouveau token (sealed box)
    pk = public.PublicKey(pub_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(new_token.encode("utf-8"))
    enc_value = base64.b64encode(sealed).decode("utf-8")

    # 4) Mettre a jour le secret IG_TOKEN
    ru = requests.put(
        f"{API}/repos/{repo}/actions/secrets/IG_TOKEN",
        headers=headers,
        data=json.dumps({"encrypted_value": enc_value, "key_id": key_id}),
    )
    if ru.status_code in (201, 204):
        print("✅ Secret GitHub IG_TOKEN mis a jour. Prochains posts programmes : OK.")
    else:
        print(f"❌ Mise a jour du secret echouee : {ru.status_code} — {ru.text[:300]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
