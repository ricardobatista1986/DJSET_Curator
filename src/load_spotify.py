"""Carga do grafo a partir da API do Spotify (100% server-side, sem browser).

Em vez do 1001tracklists (que bloqueia datacenters / Vercel), usamos as
PLAYLISTS POR GÉNERO do próprio Spotify como fonte de "sets". Cada playlist
vira um set de DJ e as faixas adjacentes viram arestas do grafo de transições
(= "o que funciona junto"). Cada faixa é enriquecida com BPM/tonalidade via
MusicBrainz→AcousticBrainz (grátis, sem chave).

Usa Client Credentials (não precisa do login do user) → corre na Vercel.
Processa em LOTES RESUMÁVEIS (uma playlist por passo) para caber no timeout
de 60s das funções serverless.
"""
import os
import time
import logging
import urllib.parse
import urllib.request
import json
from typing import Optional

logger = logging.getLogger(__name__)

SPOTIFY_API = "https://api.spotify.com/v1"


def _cc_token(cid: str, csecret: str) -> str:
    import base64
    auth = base64.b64encode(f"{cid}:{csecret}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["access_token"]


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


# --------------------------------------------------------------------------
# MusicBrainz -> AcousticBrainz (BPM / key) — best-effort, nunca fatal
# --------------------------------------------------------------------------
def _bpm_key_via_ab(artist: str, title: str) -> dict:
    out = {"bpm": None, "camelot_key": None, "energy": None,
           "danceability": None, "source": "unknown", "confidence": "low"}
    try:
        q = urllib.parse.quote(f'recording:"{title}" AND artist:"{artist}"')
        mb = _get_json(f"https://musicbrainz.org/ws/2/recording/?query={q}&fmt=json&limit=3",
                       headers={"User-Agent": "djset-curator/1.0"})
        recs = mb.get("recordings", [])
        for rec in recs:
            mbid = rec.get("id")
            if not mbid:
                continue
            try:
                ll = _get_json(f"https://acousticbrainz.org/api/v1/{mbid}/low-level",
                               headers={"User-Agent": "djset-curator/1.0"})
            except Exception:
                continue
            bpm = ll.get("rhythm", {}).get("bpm")
            key = ll.get("tonal", {}).get("key_key")
            mode = ll.get("tonal", {}).get("key_scale")
            energy = ll.get("lowlevel", {}).get("dynamic_complexity")
            if bpm or key:
                out.update({"bpm": round(bpm, 1) if bpm else None,
                            "energy": round(float(energy), 3) if energy is not None else None,
                            "source": "acousticbrainz", "confidence": "medium"})
                if key and mode:
                    out["camelot_key"] = _pitch_to_camelot(key, mode)
                return out
    except Exception as e:
        logger.debug(f"AB falhou '{artist} - {title}': {e}")
    return out


def _get_json(url: str, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def _pitch_to_camelot(key: str, mode: str) -> Optional[str]:
    A = {"C": "5A", "C#": "12A", "Db": "12A", "D": "7A", "D#": "2A", "Eb": "2A",
         "E": "9A", "F": "4A", "F#": "11A", "Gb": "11A", "G": "6A", "G#": "1A",
         "Ab": "1A", "A": "8A", "A#": "3A", "Bb": "3A", "B": "10A"}
    B = {"C": "8B", "C#": "3B", "Db": "3B", "D": "10B", "D#": "5B", "Eb": "5B",
         "E": "12B", "F": "7B", "F#": "2B", "Gb": "2B", "G": "9B", "G#": "4B",
         "Ab": "4B", "A": "11B", "A#": "6B", "Bb": "6B", "B": "1B"}
    table = B if str(mode).lower().startswith("major") else A
    return table.get(key)


# --------------------------------------------------------------------------
# Playlist discovery + processing
# --------------------------------------------------------------------------
def find_genre_playlists(token: str, genre_name: str, limit: int = 8) -> list:
    """Procura playlists do Spotify para um género (por nome)."""
    q = urllib.parse.quote(f"{genre_name} playlist")
    url = f"{SPOTIFY_API}/search?q={q}&type=playlist&limit={limit}"
    data = _get(url, token)
    items = data.get("playlists", {}).get("items", [])
    out = []
    for p in items:
        if not p:
            continue
        out.append({"id": p["id"], "name": p["name"],
                    "tracks_total": (p.get("tracks") or {}).get("total", 0),
                    "followers": (p.get("followers") or {}).get("total", 0)})
    # ordena por popularidade (seguidores)
    out.sort(key=lambda x: x["followers"], reverse=True)
    return out


def process_playlist(sb, token: str, playlist_id: str, genre_id: int,
                    max_tracks: int = 60) -> dict:
    """Lê uma playlist, grava set + tracks + transições no Supabase.
    Espelha o schema real: sets(external_id,url,...) e transitions(set_id,
    track_from_id,track_to_id,position_from,position_to). Retorna contagens."""
    pl = _get(f"{SPOTIFY_API}/playlists/{playlist_id}/tracks?limit=100&market=US", token)
    items = pl.get("items", [])
    tracks = []
    for it in items:
        tr = it.get("track")
        if not tr or not tr.get("id"):
            continue
        art = ", ".join(a["name"] for a in tr.get("artists", []))
        title = tr.get("name")
        tracks.append({"artist": art, "title": title,
                       "spotify_id": tr["id"], "preview": tr.get("preview_url")})
        if len(tracks) >= max_tracks:
            break

    if len(tracks) < 3:
        return {"status": "skip", "reason": "poucas faixas", "tracks": len(tracks)}

    # grava o set (external_id + url são UNIQUE NOT NULL)
    set_row = sb.table("sets").insert({
        "external_id": playlist_id,
        "url": f"https://open.spotify.com/playlist/{playlist_id}",
        "dj_name": "Spotify",
        "set_title": f"Spotify {playlist_id}",
        "genre_id": genre_id,
        "track_count": len(tracks),
    }).execute().data[0]
    set_id = set_row["id"]

    track_ids = []
    for t in tracks:
        tid = _upsert_track(sb, t)
        track_ids.append(tid)
        _enrich_if_needed(sb, t)
        time.sleep(0.12)

    # transições: faixa i -> faixa i+1 (funcionam juntas no set)
    transitions = [
        {"set_id": set_id, "genre_id": genre_id,
         "track_from_id": track_ids[i], "track_to_id": track_ids[i + 1],
         "position_from": i + 1, "position_to": i + 2}
        for i in range(len(track_ids) - 1)
        if track_ids[i] and track_ids[i + 1]
    ]
    saved = sum(1 for x in track_ids if x)
    if transitions:
        sb.table("transitions").insert(transitions).execute()
    return {"status": "ok", "set_id": set_id, "tracks": saved, "transitions": len(transitions)}


def _upsert_track(sb, t: dict) -> Optional[int]:
    existing = sb.table("tracks").select("id").eq("artist", t["artist"]).eq("title", t["title"]).limit(1).execute().data
    if existing:
        return existing[0]["id"]
    row = sb.table("tracks").insert({
        "artist": t["artist"], "title": t["title"],
        "spotify_id": t.get("spotify_id"), "preview_url": t.get("preview"),
        "source": "spotify", "confidence": "low",
    }).execute().data[0]
    return row["id"]


def _enrich_if_needed(sb, t: dict):
    row = sb.table("tracks").select("id,bpm,camelot_key")\
        .eq("artist", t["artist"]).eq("title", t["title"]).limit(1).execute().data
    if not row:
        return
    r = row[0]
    if r.get("bpm") or r.get("camelot_key"):
        return
    ab = _bpm_key_via_ab(t["artist"], t["title"])
    if ab.get("bpm") or ab.get("camelot_key"):
        sb.table("tracks").update({
            "bpm": ab["bpm"], "camelot_key": ab["camelot_key"],
            "energy": ab["energy"], "source": ab["source"], "confidence": ab["confidence"],
        }).eq("id", r["id"]).execute()
