"""
Modulo 3: Enriquecedor de Tracks
Cascata sincrona: Spotify API -> tunebat -> fallback.
_upsert_track_db: cria ou atualiza a track no Supabase.
"""
import re
import time
import logging
from typing import Optional
from urllib.parse import quote_plus

import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SPOTIFY_KEY_TO_CAMELOT = {
    (0,1):"8B",(1,1):"3B",(2,1):"10B",(3,1):"5B",(4,1):"12B",(5,1):"7B",
    (6,1):"2B",(7,1):"9B",(8,1):"4B",(9,1):"11B",(10,1):"6B",(11,1):"1B",
    (0,0):"5A",(1,0):"12A",(2,0):"7A",(3,0):"2A",(4,0):"9A",(5,0):"4A",
    (6,0):"11A",(7,0):"6A",(8,0):"1A",(9,0):"8A",(10,0):"3A",(11,0):"10A",
}


class Enricher:
    def __init__(self, supabase_client, spotify_client_id: str, spotify_client_secret: str):
        self.sb = supabase_client
        self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=spotify_client_id, client_secret=spotify_client_secret
        ))

    def enrich_track(self, artist: str, title: str) -> dict:
        """Enriquece uma track. Retorna dict com BPM, key, energy + confidence."""
        result = {
            "artist": artist, "title": title, "spotify_id": None,
            "bpm": None, "camelot_key": None, "energy": None,
            "danceability": None, "source": "unknown", "confidence": "low",
        }
        # Cascata
        data = self._from_spotify(artist, title)
        if data:
            result.update(data)
            result["source"] = "spotify"
            result["confidence"] = "high"
        else:
            data = self._from_tunebat(artist, title)
            if data:
                result.update(data)
                result["source"] = "tunebat"
                result["confidence"] = "medium"
            else:
                logger.warning(f"Sem dados acusticos: '{artist} - {title}'")

        self._upsert_track_db(result)
        return result

    def enrich_all_unenriched(self, batch_size: int = 50):
        """Enriquece em lote as tracks sem dados. Rode apos coleta grande."""
        tracks = (
            self.sb.table("tracks").select("id, artist, title")
            .eq("source", "unknown").limit(batch_size).execute().data
        )
        logger.info(f"Enriquecendo {len(tracks)} tracks...")
        for t in tracks:
            self.enrich_track(t["artist"], t["title"])
            time.sleep(0.5)

    # -- Spotify (search only; audio-features was deprecated by Spotify
    #    for the free tier in Nov/2024 -> 403). BPM/key now come from
    #    MusicBrainz + AcousticBrainz (see _from_acousticbrainz).) -------

    def _from_spotify(self, artist: str, title: str) -> Optional[dict]:
        """Search Spotify for the track id (used for validation/dedup) and
        enrich BPM/key/energy via MusicBrainz -> AcousticBrainz."""
        try:
            items = []
            for q in [f"{artist} {title}", f'"{title}" "{artist}"']:
                res = self.sp.search(q=q, type="track", limit=1)
                items = res.get("tracks", {}).get("items", [])
                if items:
                    break
            if not items:
                return None
            tid = items[0]["id"]
            # try AcousticBrainz chain (free, no key) for acoustic data
            ac = self._from_acousticbrainz(artist, title)
            if ac and (ac.get("bpm") or ac.get("camelot_key")):
                ac["spotify_id"] = tid
                return ac
            # no acoustic data from AB -> return None so the cascade can try
            # tunebat (and the caller still has the Spotify id for validation)
            return None
        except Exception as e:
            logger.debug(f"Spotify falhou '{artist} - {title}': {e}")
            return None

    # -- AcousticBrainz (free, no API key) ----------------------------
    # Chain: MusicBrainz recording search (gets MBID) -> AcousticBrainz
    # low-level (gets bpm + key/mode) -> Camelot conversion.

    def _mbid_for(self, artist: str, title: str) -> Optional[str]:
        try:
            url = "https://musicbrainz.org/ws/2/recording/"
            params = {"query": f'recording:"{title}" AND artist:"{artist}"',
                      "fmt": "json", "limit": 1}
            r = requests.get(url, params=params,
                             headers={"User-Agent": "djset-curator/1.0"}, timeout=10)
            if r.status_code != 200:
                return None
            recs = r.json().get("recordings", [])
            return recs[0]["id"] if recs else None
        except Exception:
            return None

    def _from_acousticbrainz(self, artist: str, title: str) -> Optional[dict]:
        try:
            mbid = self._mbid_for(artist, title)
            if not mbid:
                return None
            r = requests.get(
                f"https://acousticbrainz.org/api/v1/{mbid}/low-level",
                headers={"User-Agent": "djset-curator/1.0"}, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            bpm = data.get("rhythm", {}).get("bpm")
            key = data.get("tonal", {}).get("key_key")      # e.g. "C"
            mode = data.get("tonal", {}).get("key_scale")    # "major"/"minor"
            energy = data.get("lowlevel", {}).get("dynamic_complexity")
            # map (key name, mode) -> Camelot. MusicBrainz uses pitch class 0=C.
            PITCH_TO_CAMELOT_A = {  # minor
                "C": "5A", "C#": "12A", "D": "7A", "D#": "2A", "E": "9A",
                "F": "4A", "F#": "11A", "G": "6A", "G#": "1A", "A": "8A",
                "A#": "3A", "B": "10A"}
            PITCH_TO_CAMELOT_B = {  # major
                "C": "8B", "C#": "3B", "D": "10B", "D#": "5B", "E": "12B",
                "F": "7B", "F#": "2B", "G": "9B", "G#": "4B", "A": "11B",
                "A#": "6B", "B": "1B"}
            camelot = None
            if key and mode:
                table = PITCH_TO_CAMELOT_B if mode.lower().startswith("major") else PITCH_TO_CAMELOT_A
                camelot = table.get(key)
            return {
                "spotify_id": None,
                "bpm": round(bpm, 1) if bpm else None,
                "camelot_key": camelot,
                "energy": round(float(energy), 3) if energy is not None else None,
                "danceability": None,
            }
        except Exception as e:
            logger.debug(f"AcousticBrainz falhou '{artist} - {title}': {e}")
            return None

    # -- Tunebat (secondary fallback) --------------------------------

    def _from_tunebat(self, artist: str, title: str) -> Optional[dict]:
        try:
            q    = quote_plus(f"{artist} {title}")
            url  = f"https://tunebat.com/Search?q={q}"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            bpm, camelot = None, None
            bpm_el = soup.find(class_=re.compile(r"bpm|tempo", re.I))
            if bpm_el:
                m = re.search(r"(\d+(?:\.\d+)?)", bpm_el.get_text(strip=True))
                if m:
                    bpm = float(m.group(1))
            key_el = soup.find(class_=re.compile(r"key|camelot", re.I))
            if key_el:
                m = re.search(r"(\d{1,2}[AB])", key_el.get_text(strip=True))
                if m:
                    camelot = m.group(1)
            return {"bpm": bpm, "camelot_key": camelot} if (bpm or camelot) else None
        except Exception as e:
            logger.debug(f"Tunebat falhou '{artist} - {title}': {e}")
            return None

    # -- Persistencia ------------------------------------------------

    def _upsert_track_db(self, data: dict):
        """Cria ou atualiza a track no Supabase."""
        try:
            existing = (
                self.sb.table("tracks").select("id")
                .eq("artist", data["artist"]).eq("title", data["title"])
                .execute().data
            )
            payload = {
                "spotify_id":   data.get("spotify_id"),
                "bpm":          data.get("bpm"),
                "camelot_key":  data.get("camelot_key"),
                "energy":       data.get("energy"),
                "danceability": data.get("danceability"),
                "source":       data.get("source", "unknown"),
                "confidence":   data.get("confidence", "low"),
            }
            if existing:
                self.sb.table("tracks").update(payload).eq("id", existing[0]["id"]).execute()
            else:
                payload["artist"] = data["artist"]
                payload["title"]  = data["title"]
                self.sb.table("tracks").insert(payload).execute()
        except Exception as e:
            logger.error(f"Erro ao salvar track no DB: {e}")
