"""
Modulo 4: Motor de Curadoria
build_set() e sincrono — sem await nos notebooks.
Usa google-genai SDK (nova, nao depreciada).
"""
import logging
from typing import Optional

import google.genai as genai

from src.enricher.enricher import Enricher
from src.graph.graph import Graph
from src.llm.llm import LLMProvider

logger = logging.getLogger(__name__)


class Curator:
    def __init__(self, supabase_client, enricher: Enricher, graph: Graph,
                 gemini_api_key: str = None, llm_provider: LLMProvider = None):
        self.sb       = supabase_client
        self.enricher = enricher
        self.graph    = graph
        self.llm      = llm_provider or LLMProvider()

    # -- API PUBLICA -------------------------------------------------

    def build_set(self, tracks: list, genre_slug: str,
                  list_name: str = "Meu Set", save_to_db: bool = True) -> dict:
        """
        Gera tracklist ordenada. Retorna dict com output_text, tracks_enriched, suggestions.
        tracks: lista de strings "Artista - Titulo"
        """
        genre = self._get_genre(genre_slug)
        if not genre:
            raise ValueError(f"Genero '{genre_slug}' nao encontrado.")

        print(f"[1/4] Enriquecendo {len(tracks)} tracks...")
        enriched = self._enrich_tracks(tracks)

        print("[2/4] Consultando grafo de transicoes...")
        graph_ctx = self._build_graph_context(enriched, genre["id"])

        print("[3/4] Identificando sugestoes externas...")
        suggestions = self._find_suggestions(enriched, graph_ctx)

        print("[4/4] Gerando tracklist com Gemini 2.0 Flash...")
        stats  = self.graph.get_genre_stats(genre["id"])
        output = self._call_gemini(enriched, graph_ctx, suggestions, genre, stats)

        result = {
            "output_text":     output,
            "proposed_set_id": None,
            "tracks_enriched": enriched,
            "suggestions":     suggestions,
        }

        if save_to_db:
            result["proposed_set_id"] = self._save_proposed_set(
                enriched, output, genre, list_name
            )
        return result

    # -- ETAPAS INTERNAS ---------------------------------------------

    def _enrich_tracks(self, tracks: list) -> list:
        enriched = []
        for raw in tracks:
            artist, title = self._parse_track_string(raw)
            data = self.enricher.enrich_track(artist, title)
            data["raw_input"] = raw
            track_id = self.graph.find_track_id(artist, title)
            data["track_id"] = track_id
            if track_id:
                pos = self.graph.get_typical_position(track_id)
                data["typical_zone"]     = pos.get("typical_zone", "unknown")
                data["avg_position_pct"] = pos.get("avg_position_pct", 0.5)
            else:
                data["typical_zone"]     = "unknown"
                data["avg_position_pct"] = 0.5
            enriched.append(data)
        return enriched

    def _build_graph_context(self, enriched: list, genre_id: int) -> list:
        context = []
        for t in enriched:
            tid   = t.get("track_id")
            entry = {"artist": t["artist"], "title": t["title"],
                     "successors": [], "predecessors": []}
            if tid:
                entry["successors"]   = self.graph.get_successors(tid, genre_id, top_n=15)
                entry["predecessors"] = self.graph.get_predecessors(tid, genre_id, top_n=15)
            context.append(entry)
        return context

    def _find_suggestions(self, enriched: list, graph_ctx: list) -> list:
        my_ids = {t.get("track_id") for t in enriched if t.get("track_id")}
        seen   = {}
        for i, ctx in enumerate(graph_ctx):
            for s in ctx["successors"]:
                sid = s.get("id")
                if sid and sid not in my_ids and s.get("count", 0) >= 3:
                    if sid not in seen or s["count"] > seen[sid]["count"]:
                        seen[sid] = {
                            "after_track":    f"{ctx['artist']} - {ctx['title']}",
                            "after_position": i,
                            "track_id":       sid,
                            "artist":         s.get("artist"),
                            "title":          s.get("title"),
                            "count":          s.get("count"),
                            "bpm":            s.get("bpm"),
                            "camelot_key":    s.get("camelot_key"),
                            "spotify_id":     s.get("spotify_id"),
                        }
        return sorted(seen.values(), key=lambda x: x["count"], reverse=True)[:10]

    def _call_gemini(self, enriched: list, graph_ctx: list,
                     suggestions: list, genre: dict, stats: dict) -> str:
        # Monta texto das tracks
        tracks_text = ""
        for i, t in enumerate(enriched, 1):
            bpm  = f"BPM {t['bpm']}"  if t.get("bpm")          else "BPM ?"
            key  = f"Key {t['camelot_key']}" if t.get("camelot_key") else "Key ?"
            eng  = f"Energy {t['energy']}"   if t.get("energy")     else ""
            warn = " [ATENCAO: dados incompletos]" if t.get("confidence") == "low" else ""
            tracks_text += f"{i:02d}. {t['artist']} - {t['title']} | {bpm} | {key} | {eng} | zona: {t.get('typical_zone','?')}{warn}\n"

        # Monta texto do grafo
        graph_text = ""
        for ctx in graph_ctx:
            top = ctx["successors"][:5]
            if top:
                succs = ", ".join(f"'{s.get('artist')} - {s.get('title')}' ({s.get('count')}x)" for s in top)
                graph_text += f"- Apos '{ctx['artist']} - {ctx['title']}': {succs}\n"

        # Monta sugestoes
        sugg_text = ""
        for s in suggestions[:8]:
            bpm = f"BPM {s['bpm']}" if s.get("bpm") else ""
            key = f"Key {s['camelot_key']}" if s.get("camelot_key") else ""
            sugg_text += f"- '{s['artist']} - {s['title']}' apos '{s['after_track']}' ({s['count']}x) {bpm} {key}\n"

        prompt = f"""Voce e um DJ especializado em {genre['name']}.
Base de conhecimento: {stats.get('sets', 0)} sets reais, {stats.get('transitions', 0)} transicoes.

SUAS TRACKS ({len(enriched)} total):
{tracks_text}

TRANSICOES MAIS FREQUENTES EM SETS REAIS:
{graph_text if graph_text else 'Base ainda em construcao para essas tracks.'}

SUGESTOES EXTERNAS (tracks que aparecem entre as suas em sets reais):
{sugg_text if sugg_text else 'Nenhuma sugestao com frequencia suficiente ainda.'}

INSTRUCOES:
1. Ordene TODAS as suas tracks da forma mais fluida possivel
2. Para cada transicao, explique em 1 linha o motivo (BPM, key, energia)
3. Indique onde sugestoes externas se encaixam (marque com SUGESTAO EXTERNA)
4. Marque com ATENCAO as tracks com dados incompletos
5. Finalize com 3 notas sobre o arco energetico do set

FORMATO:
TRACKLIST - {genre['name']}

01. Artista - Track | BPM | Key | zona
    Transicao: motivo

SUGESTOES EXTERNAS:
- Artista - Track (Nx em sets reais) | onde encaixar

NOTAS DO SET:
1. Arco energetico: ...
2. Coerencia de keys: ...
3. Ponto de atencao: ..."""

        try:
            out = self.llm.complete(prompt, max_tokens=1500)
            if out.startswith("__LLM_FAIL__"):
                logger.warning("LLM falhou, usando fallback determinístico")
                return self._deterministic_output(enriched, graph_ctx, suggestions)
            return out
        except Exception as e:
            logger.error(f"Erro LLM: {e}")
            return self._deterministic_output(enriched, graph_ctx, suggestions)

    def _deterministic_output(self, enriched, graph_ctx, suggestions) -> str:
        """Ordenação por grafo/energia quando a LLM não está disponível
        (sem custo, funciona sempre)."""
        def keyf(t):
            return (t.get("bpm") or 0, t.get("energy") or 0)
        ordered = sorted(enriched, key=keyf)
        lines = ["TRACKLIST (modo determinístico — sem IA)\n"]
        for i, t in enumerate(ordered, 1):
            bpm = f"BPM {t['bpm']}" if t.get("bpm") else "BPM ?"
            key = f"Key {t['camelot_key']}" if t.get("camelot_key") else "Key ?"
            lines.append(f"{i:02d}. {t['artist']} - {t['title']} | {bpm} | {key}")
            # sugestão que encaixa aqui
            for s in suggestions:
                if s.get("after_track") == f"{t['artist']} - {t['title']}":
                    lines.append(f"    SUGESTAO EXTERNA: {s['artist']} - {s['title']} ({s.get('count')}x)")
        if suggestions:
            lines.append("\nSUGESTOES EXTERNAS (grafo):")
            for s in suggestions[:8]:
                lines.append(f"- {s['artist']} - {s['title']} ({s.get('count')}x) apos {s.get('after_track')}")
        lines.append("\nNOTAS: ordem por BPM/energia crescente (fallback sem LLM).")
        return "\n".join(lines)

    # -- PERSISTENCIA ------------------------------------------------

    def _save_proposed_set(self, enriched: list, output: str,
                           genre: dict, list_name: str) -> Optional[int]:
        try:
            ul_id = self.sb.table("user_lists").insert({
                "name": list_name, "genre_id": genre["id"]
            }).execute().data[0]["id"]

            ps_id = self.sb.table("proposed_sets").insert({
                "user_list_id": ul_id, "genre_id": genre["id"], "raw_output": output
            }).execute().data[0]["id"]

            rows = [
                {"proposed_set_id": ps_id, "position": i+1,
                 "track_id": t.get("track_id"), "is_suggestion": False,
                 "confidence": t.get("confidence", "low")}
                for i, t in enumerate(enriched)
            ]
            if rows:
                self.sb.table("proposed_set_tracks").insert(rows).execute()
            return ps_id
        except Exception as e:
            logger.error(f"Erro ao salvar set proposto: {e}")
            return None

    # -- HELPERS -----------------------------------------------------

    def _get_genre(self, slug: str) -> Optional[dict]:
        r = self.sb.table("genres").select("*").eq("slug", slug).execute().data
        return r[0] if r else None

    def _parse_track_string(self, raw: str):
        if " - " in raw:
            p = raw.split(" - ", 1)
            return p[0].strip(), p[1].strip()
        return raw.strip(), raw.strip()
