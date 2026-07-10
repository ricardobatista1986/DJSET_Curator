#!/usr/bin/env python3
"""
DJ Set Curator — Setup & Smoke Test (one-shot)
===============================================
Aplica o schema + RPC no Supabase, popula os géneros e corre um teste de fumo
do motor de curadoria contra um dataset pequeno.

Como correr (na TUA máquina, com rede + chaves válidas):
    . .venv/bin/activate
    python setup_and_smoke_test.py

Pré-requisitos no .env:
    SUPABASE_URL, SUPABASE_KEY          (anon/public key — leitura/escrita se RLS ok)
    SUPABASE_SERVICE_KEY                (opcional; NECESSÁRIO para criar tabelas via script)
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    GEMINI_API_KEY

Notas:
- Se as tabelas já existirem, o script não as recria (IF NOT EXISTS).
- Se não tiveres SUPABASE_SERVICE_KEY, aplica config/schema.sql e
  config/rpc_functions.sql manualmente no SQL Editor do Supabase e corre
  este script com --skip-schema.
- A coleta de 1001tracklists pode estar bloqueada por anti-bot conforme a rede;
  este script NÃO depende dela para o smoke test (usa dados de exemplo).
"""
import argparse
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

from supabase import create_client


def step(msg):
    print(f"\n=== {msg} ===")


def apply_schema(sb):
    """Apply schema + RPC. Needs a client with DDL rights (service role)."""
    import pathlib
    base = pathlib.Path(__file__).parent
    sql_files = ["config/schema.sql", "config/rpc_functions.sql"]
    for f in sql_files:
        p = base / f
        sql = p.read_text()
        # Supabase SQL editor endpoint isn't exposed via the anon client;
        # the supported way from code is rpc('exec_sql', {...}) OR running in
        # the dashboard. We attempt the dashboard-style endpoint via REST.
        # If this fails, the user must paste the SQL in the dashboard.
        try:
            # Many setups expose a `exec_sql` RPC; try it.
            sb.rpc("exec_sql", {"query": sql}).execute()
            print(f"  aplicado: {f}")
        except Exception as e:
            print(f"  AVISO: não consegui aplicar {f} via RPC ({e}).")
            print(f"         Aplica manualmente no SQL Editor do Supabase: {p}")


def seed_genres(sb):
    try:
        r = sb.table("genres").select("id", count="exact").execute()
        if r.count and r.count > 0:
            print(f"  géneros já populados ({r.count}).")
            return
    except Exception:
        print("  tabela genres indisponível (schema não aplicado?).")
        return
    genres = [
        ("goa-psy-trance", "Goa / Psy-Trance"), ("techno", "Techno"),
        ("tech-house", "Tech House"), ("house", "House"),
        ("deep-house", "Deep House"), ("progressive-house", "Progressive House"),
        ("melodic-house-techno", "Melodic House / Techno"),
        ("minimal-deep-tech", "Minimal / Deep Tech"), ("trance", "Trance"),
        ("drum-bass", "Drum & Bass"), ("dubstep", "Dubstep"),
        ("hard-dance", "Hard Dance"), ("bass-house", "Bass House"),
        ("breaks", "Breaks"), ("afro-house", "Afro House"),
        ("indie-dance", "Indie Dance"), ("electronica", "Electronica"),
        ("organic-house-downtempo", "Organic House / Downtempo"),
        ("mainstage", "Mainstage"),
    ]
    sb.table("genres").insert(
        [{"slug": s, "name": n, "active": True} for s, n in genres]
    ).execute()
    print(f"  inseridos {len(genres)} géneros.")


def smoke_test_graph():
    """Exercício do motor de grafo + sugestões com dados de exemplo
    (não precisa de rede)."""
    step("Smoke test: Graph + sugestões (dataset de exemplo)")
    # in-memory fake supabase with a small psytrance graph
    class SeededSB:
        def __init__(self):
            self.tracks = [
                (1, "Vini Vici", "The Tribe", 138, "9A", 0.79, "high"),
                (2, "Astrix", "Basic", 140, "9A", 0.82, "high"),
                (3, "Neelix", "Supersonic", 141, "6B", 0.85, "high"),
                (4, "Infected Mushroom", "Psycho", 143, "8A", 0.88, "high"),
                (5, "Hallucinogen", "LSD", 145, "10A", 0.81, "high"),
            ]
            self.transitions = [
                (1, 1, 1, 2), (2, 1, 2, 3), (3, 1, 3, 4), (4, 1, 4, 5),
                (5, 1, 1, 3), (6, 1, 3, 5), (7, 1, 2, 5), (8, 1, 1, 4), (9, 1, 5, 2),
            ]
            self.genres = [{"id": 1, "slug": "goa-psy-trance", "name": "Goa / Psy-Trance"}]

        def table(self, name):
            sb = self

            class T:
                def __init__(self):
                    self._id = None
                def select(self, *a, **k): return self
                def eq(self, col, val):
                    if col == "id": self._id = val
                    return self
                def ilike(self, *a, **k): return self
                def limit(self, *a, **k): return self
                def insert(self, row):
                    class R: data = [{"id": 1}]
                    return R()
                def update(self, row): return self
                def execute(self):
                    if name == "tracks":
                        data = [dict(id=t[0], artist=t[1], title=t[2], bpm=t[3],
                                     camelot_key=t[4], energy=t[5], confidence=t[6])
                                for t in sb.tracks if self._id is None or t[0] == self._id]
                    elif name == "transitions":
                        data = [dict(track_from_id=t[2], track_to_id=t[3], genre_id=t[1])
                                for t in sb.transitions]
                    elif name == "genres":
                        data = sb.genres
                    else:
                        data = [{"id": 1}]
                    class R: pass
                    R.data = data; R.count = len(data)
                    return R()
            return T()

        def rpc(self, name, params):
            class R: data = []
            return R()

    from src.graph.graph import Graph
    g = Graph(SeededSB())
    my = [1, 2]
    cnt = {}
    for tid in my:
        for s in g.get_successors(tid, 1, 15):
            if s["id"] not in my:
                cnt[s["id"]] = cnt.get(s["id"], 0) + s["count"]
    sug = [(sid, c) for sid, c in cnt.items() if c >= 3]
    assert sug, "esperava sugestões externas"
    print("  sugestões externas (count>=3):")
    for sid, c in sorted(sug, key=lambda x: -x[1]):
        tr = next(t for t in SeededSB().tracks if t[0] == sid)
        print(f"    + {tr[1]} - {tr[2]}  count={c}  BPM {tr[3]} Key {tr[4]}")
    print("  ✅ Graph + sugestões OK")


def smoke_test_enricher(sb):
    step("Smoke test: Enricher (Spotify + AcousticBrainz)")
    from src.enricher.enricher import Enricher
    en = Enricher(sb, os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"])
    for a, t in [("Infected Mushroom", "Psycho"), ("Vini Vici", "The Tribe")]:
        r = en.enrich_track(a, t)
        print(f"  {a} - {t}: BPM={r['bpm']} Key={r['camelot_key']} "
              f"Energy={r['energy']} src={r['source']} conf={r['confidence']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-schema", action="store_true",
                    help="não tenta aplicar schema (já aplicado no dashboard)")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Falta SUPABASE_URL / SUPABASE_KEY no .env"); sys.exit(1)

    sb = create_client(url, key)

    step("1. Schema + RPC")
    if args.skip_schema:
        print("  ignorado (--skip-schema)")
    else:
        svc = os.environ.get("SUPABASE_SERVICE_KEY")
        if svc:
            apply_schema(create_client(url, svc))
        else:
            print("  SUPABASE_SERVICE_KEY ausente -> aplica config/schema.sql e "
                  "config/rpc_functions.sql no SQL Editor do Supabase e corre com --skip-schema.")

    step("2. Géneros")
    seed_genres(sb)

    step("3. Smoke test do motor (sem rede)")
    smoke_test_graph()

    if os.environ.get("SPOTIFY_CLIENT_ID"):
        step("4. Smoke test do Enricher (rede)")
        smoke_test_enricher(sb)
    else:
        print("\nSalta enricher (sem SPOTIFY creds).")

    print("\n✅ Setup & smoke test concluído. Próximo passo: notebook 01 (coleta) "
          "ou 04 (curadoria) no teu ambiente.")


if __name__ == "__main__":
    main()
