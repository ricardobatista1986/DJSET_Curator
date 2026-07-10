"""OAuth Spotify para leitura de playlists do utilizador.

O Spotify exige autenticação de utilizador (OAuth) para ler playlists,
mesmo públicas. Fluxo:
  1. GET /api/spotify/login  -> devolve a URL de consentimento
  2. User autoriza no Spotify -> redirect p/ /api/spotify/callback?code=...
  3. Trocamos o code por access+refresh token -> guardamos na sessão (cookie assinado)
  4. Leitura de playlists usa o token do user.

Para um app de utilizador único, guardar o token na sessão (cookie assinado
do Flask) é suficiente e funciona em serverless (Vercel), pois o cookie vem
do browser em cada pedido.
"""
import os
import time
import logging

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = "playlist-read-private playlist-read-collaborative"


def redirect_uri() -> str:
    # Permite override via env; default = Vercel. Em local usa localhost.
    return os.environ.get("SPOTIFY_REDIRECT_URI",
                           "https://djset-curator.vercel.app/api/spotify/callback")


def client_id() -> str:
    return os.environ.get("SPOTIFY_CLIENT_ID", "")


def client_secret() -> str:
    return os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def authorize_url(state: str) -> str:
    cid = client_id()
    ru = redirect_uri()
    return (f"{AUTH_URL}?response_type=code&client_id={cid}"
            f"&scope={SCOPES}&redirect_uri={ru}&state={state}")


def exchange_code(code: str) -> dict:
    import requests
    import base64
    cid, sec = client_id(), client_secret()
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }, headers={"Authorization": f"Basic {basic}"})
    r.raise_for_status()
    return r.json()


def refresh_token(refresh: str) -> dict:
    import requests
    import base64
    cid, sec = client_id(), client_secret()
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    }, headers={"Authorization": f"Basic {basic}"})
    r.raise_for_status()
    return r.json()


def tracks_from_playlist_with_token(access_token: str, playlist_url: str) -> list:
    """Lê faixas de uma playlist com o token de utilizador."""
    from urllib.parse import quote
    import requests
    import re
    m = re.search(r"playlist/([A-Za-z0-9]+)", playlist_url)
    if not m:
        raise ValueError("URL de playlist Spotify inválida.")
    pid = m.group(1)
    out = []
    url = f"https://api.spotify.com/v1/playlists/{pid}/tracks?limit=100"
    while url:
        r = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            tr = item.get("track")
            if not tr:
                continue
            art = ", ".join(a["name"] for a in tr.get("artists", []))
            out.append(f"{art} - {tr['name']}")
        url = data.get("next")
    return out


def get_valid_token(session: dict) -> str:
    """Devolve um access token válido, refrescando se preciso.
    session = flask.session (dict-like)."""
    tok = session.get("spotify_token")
    if not tok:
        return None
    if tok.get("expires_at", 0) < time.time() + 60:
        try:
            new = refresh_token(tok["refresh_token"])
            tok["access_token"] = new["access_token"]
            tok["expires_at"] = time.time() + new.get("expires_in", 3600)
            if "refresh_token" in new:
                tok["refresh_token"] = new["refresh_token"]
            session["spotify_token"] = tok
        except Exception as e:
            logger.error(f"refresh falhou: {e}")
            return None
    return tok["access_token"]
