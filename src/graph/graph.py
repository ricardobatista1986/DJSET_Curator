"""
Modulo 2: Grafo de Transicoes
Queries sincronas sobre o grafo no Supabase.
genre_id=None = todos os generos.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Graph:
    def __init__(self, supabase_client):
        self.sb = supabase_client

    def get_successors(self, track_id: int, genre_id: int, top_n: int = 15) -> list:
        try:
            r = self.sb.rpc("get_successors", {
                "p_track_id": track_id, "p_genre_id": genre_id, "p_top_n": top_n
            }).execute()
            return r.data or []
        except Exception:
            return self._successors_manual(track_id, genre_id, top_n)

    def get_predecessors(self, track_id: int, genre_id: int, top_n: int = 15) -> list:
        try:
            r = self.sb.rpc("get_predecessors", {
                "p_track_id": track_id, "p_genre_id": genre_id, "p_top_n": top_n
            }).execute()
            return r.data or []
        except Exception:
            return self._predecessors_manual(track_id, genre_id, top_n)

    def get_transition_count(self, from_id: int, to_id: int, genre_id: int) -> int:
        r = (
            self.sb.table("transitions").select("id", count="exact")
            .eq("track_from_id", from_id).eq("track_to_id", to_id)
            .eq("genre_id", genre_id).execute()
        )
        return r.count or 0

    def get_typical_position(self, track_id: int, genre_id: Optional[int] = None) -> dict:
        """Posicao tipica da track (0.0-1.0). genre_id=None = todos os generos."""
        q = (
            self.sb.table("transitions")
            .select("position_from, sets!inner(track_count)")
            .eq("track_from_id", track_id)
        )
        if genre_id is not None and genre_id > 0:
            q = q.eq("genre_id", genre_id)

        rows = q.limit(200).execute().data

        if not rows:
            return {"avg_position_pct": 0.5, "typical_zone": "middle"}

        pcts = []
        for r in rows:
            tc = (r.get("sets") or {}).get("track_count", 0)
            if tc and tc > 0:
                pcts.append(r["position_from"] / tc)

        if not pcts:
            return {"avg_position_pct": 0.5, "typical_zone": "middle"}

        avg = sum(pcts) / len(pcts)
        if   avg < 0.20: zone = "opening"
        elif avg < 0.45: zone = "buildup"
        elif avg < 0.70: zone = "peak"
        elif avg < 0.85: zone = "comedown"
        else:            zone = "closing"

        return {"avg_position_pct": round(avg, 2), "typical_zone": zone}

    def find_track_id(self, artist: str, title: str) -> Optional[int]:
        r = (
            self.sb.table("tracks").select("id")
            .ilike("artist", artist).ilike("title", title)
            .execute().data
        )
        return r[0]["id"] if r else None

    def get_track_data(self, track_id: int) -> Optional[dict]:
        r = self.sb.table("tracks").select("*").eq("id", track_id).execute().data
        return r[0] if r else None

    def get_genre_stats(self, genre_id: Optional[int]) -> dict:
        q_sets = self.sb.table("sets").select("id", count="exact")
        q_tr   = self.sb.table("transitions").select("id", count="exact")
        if genre_id is not None:
            q_sets = q_sets.eq("genre_id", genre_id)
            q_tr   = q_tr.eq("genre_id", genre_id)
        sets_n  = q_sets.execute().count or 0
        trans_n = q_tr.execute().count or 0
        return {"sets": sets_n, "transitions": trans_n}

    def get_top_nodes(self, genre_id: Optional[int] = None, limit: int = 30) -> list:
        """Nós (tracks) com maior grau no grafo — para explorar o catálogo."""
        q = self.sb.table("transitions").select("track_from_id, track_to_id")
        if genre_id is not None:
            q = q.eq("genre_id", genre_id)
        rows = q.execute().data
        deg = {}
        for r in rows:
            for tid in (r.get("track_from_id"), r.get("track_to_id")):
                if tid:
                    deg[tid] = deg.get(tid, 0) + 1
        top = sorted(deg.items(), key=lambda x: x[1], reverse=True)[:limit]
        out = []
        for tid, d in top:
            t = self.get_track_data(tid)
            if t:
                t["degree"] = d
                out.append(t)
        return out

    def _successors_manual(self, track_id: int, genre_id: int, top_n: int) -> list:
        rows = (
            self.sb.table("transitions").select("track_to_id")
            .eq("track_from_id", track_id).eq("genre_id", genre_id).execute().data
        )
        counts = {}
        for r in rows:
            tid = r["track_to_id"]
            counts[tid] = counts.get(tid, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        results = []
        for tid, cnt in top:
            t = self.get_track_data(tid)
            if t:
                t["count"] = cnt
                results.append(t)
        return results

    def _predecessors_manual(self, track_id: int, genre_id: int, top_n: int) -> list:
        rows = (
            self.sb.table("transitions").select("track_from_id")
            .eq("track_to_id", track_id).eq("genre_id", genre_id).execute().data
        )
        counts = {}
        for r in rows:
            tid = r["track_from_id"]
            counts[tid] = counts.get(tid, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        results = []
        for tid, cnt in top:
            t = self.get_track_data(tid)
            if t:
                t["count"] = cnt
                results.append(t)
        return results
